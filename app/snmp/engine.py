"""
SNMP Engine — pysnmp asyncio wrapper.

提供三個核心操作：
- get()      — 取得一或多個 scalar OID 的值
- walk()     — 走訪整個 OID 子樹（自動使用 GETBULK）
- get_bulk() — 單次 GETBULK 請求

所有操作都是 async，使用 pysnmp-lextudio v6.x 的 asyncio API。

NOTE: pysnmp imports are deferred to AsyncSnmpEngine.__init__() so that
mock mode (SNMP_MOCK=true) works even when pysnmp is not installed.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Hard cap for per-PDU wait_for timeout (seconds).
# Even if SNMP_TIMEOUT is set very high, a single PDU should never
# block the event loop for more than this.
_MAX_PDU_WAIT: float = 30.0


class SnmpError(Exception):
    """Base SNMP error."""


class SnmpTimeoutError(SnmpError):
    """SNMP request timed out after all retries."""


class SnmpNoSuchObjectError(SnmpError):
    """Requested OID does not exist on the device."""


# Seconds to wait before closing a timed-out engine.
# When wait_for() cancels a pysnmp getCmd/bulkCmd, the underlying UDP
# transport still has pending callbacks in uvloop.  Closing the dispatcher
# immediately causes AbstractTransportDispatcher._cbFun exceptions.
# Deferring cleanup lets pending callbacks drain first.
_DEFERRED_CLOSE_DELAY: float = 3.0


@dataclass
class SnmpTarget:
    """Connection parameters for a single SNMP target."""

    ip: str
    community: str
    port: int = 161
    timeout: float = 5.0
    retries: int = 2


@dataclass
class SnmpEngineConfig:
    """Engine-level configuration."""

    max_repetitions: int = 25
    walk_timeout: float = 120.0


def _pdu_timeout(target: SnmpTarget) -> float:
    """Compute per-PDU hard timeout, capped at _MAX_PDU_WAIT."""
    natural = target.timeout * (target.retries + 1) + 2
    return min(natural, _MAX_PDU_WAIT)


class AsyncSnmpEngine:
    """
    Thin async wrapper around pysnmp-lextudio v6.x asyncio API.

    Each get()/walk() call creates its own short-lived PySnmpEngine
    so that concurrent operations never share transport dispatcher
    state. This eliminates cross-contamination when a request hangs
    and must be cancelled.
    """

    def __init__(self, config: SnmpEngineConfig | None = None) -> None:
        # Only validate that pysnmp is importable at init time
        from pysnmp.hlapi.asyncio import SnmpEngine as _PySnmpEngine  # noqa: F401

        self._config = config or SnmpEngineConfig()

    @staticmethod
    def _new_engine() -> Any:
        """Create a fresh, isolated PySnmpEngine instance."""
        from pysnmp.hlapi.asyncio import SnmpEngine as PySnmpEngine

        return PySnmpEngine()

    @staticmethod
    def _close_engine(engine: Any) -> None:
        """Best-effort cleanup of a PySnmpEngine's transport dispatcher."""
        try:
            if hasattr(engine, "transportDispatcher"):
                engine.transportDispatcher.closeDispatcher()
        except Exception:
            pass

    @staticmethod
    def _deferred_close_engine(engine: Any) -> None:
        """Schedule engine cleanup after a delay.

        Used after wait_for() cancels a hung PDU — pending uvloop callbacks
        need time to drain before we tear down the transport dispatcher.
        Avoids AbstractTransportDispatcher._cbFun exceptions.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(
                _DEFERRED_CLOSE_DELAY,
                AsyncSnmpEngine._close_engine,
                engine,
            )
        except Exception:
            # Fallback: close immediately if event loop unavailable
            AsyncSnmpEngine._close_engine(engine)

    @staticmethod
    def _make_transport(target: SnmpTarget) -> Any:
        """Create UDP transport for target."""
        from pysnmp.hlapi.asyncio import UdpTransportTarget

        return UdpTransportTarget(
            (target.ip, target.port),
            timeout=target.timeout,
            retries=target.retries,
        )

    async def get(
        self, target: SnmpTarget, *oids: str,
    ) -> dict[str, Any]:
        """
        SNMP GET for one or more scalar OIDs.

        Returns:
            {oid_str: value} dict.

        Raises:
            SnmpTimeoutError: if request times out.
            SnmpError: on other SNMP errors.
        """
        from pysnmp.hlapi.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            getCmd,
        )

        engine = self._new_engine()
        transport = self._make_transport(target)
        object_types = [
            ObjectType(ObjectIdentity(oid)) for oid in oids
        ]
        pdu_timeout = _pdu_timeout(target)

        try:
            error_indication, error_status, error_index, var_binds = (
                await asyncio.wait_for(
                    getCmd(
                        engine,
                        CommunityData(target.community),
                        transport,
                        ContextData(),
                        *object_types,
                    ),
                    timeout=pdu_timeout,
                )
            )
        except asyncio.TimeoutError:
            logger.warning(
                "getCmd hung for %s (>%.0fs)",
                target.ip, pdu_timeout,
            )
            # Deferred close: let pending uvloop callbacks drain first
            self._deferred_close_engine(engine)
            raise SnmpTimeoutError(
                f"SNMP GET hung: {target.ip} OIDs={oids}"
            )

        if error_indication:
            err_str = str(error_indication)
            if "timeout" in err_str.lower() or "request" in err_str.lower():
                self._close_engine(engine)
                raise SnmpTimeoutError(
                    f"SNMP GET timeout: {target.ip} OIDs={oids}"
                )
            self._close_engine(engine)
            raise SnmpError(f"SNMP GET error: {err_str}")

        if error_status:
            self._close_engine(engine)
            raise SnmpError(
                f"SNMP GET error status: {error_status.prettyPrint()} "
                f"at {var_binds[int(error_index) - 1][0] if error_index else '?'}"
            )

        result: dict[str, Any] = {}
        for oid, val in var_binds:
            oid_str = str(oid)
            val_str = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)

            val_class = val.__class__.__name__
            if val_class in ("NoSuchObject", "NoSuchInstance", "EndOfMibView"):
                continue

            result[oid_str] = val_str

        self._close_engine(engine)
        return result

    async def walk(
        self,
        target: SnmpTarget,
        oid_prefix: str,
        max_repetitions: int | None = None,
    ) -> list[tuple[str, str]]:
        """
        Full SNMP walk of a subtree using GETBULK.

        Each walk creates its own PySnmpEngine so concurrent walks
        never interfere with each other.

        Returns:
            List of (oid_str, value_str) tuples within the subtree.

        Raises:
            SnmpTimeoutError: if any GETBULK times out or walk exceeds deadline.
            SnmpError: on other errors.
        """
        from pysnmp.hlapi.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            bulkCmd,
        )

        engine = self._new_engine()
        max_rep = max_repetitions or self._config.max_repetitions
        transport = self._make_transport(target)
        results: list[tuple[str, str]] = []
        prefix = oid_prefix.rstrip(".")
        deadline = _time.monotonic() + self._config.walk_timeout
        pdu_timeout = _pdu_timeout(target)
        _pdu_hung = False  # track whether a PDU-level timeout occurred

        current_oid = ObjectIdentity(prefix)
        community = CommunityData(target.community)
        context = ContextData()

        try:
            while True:
                if _time.monotonic() > deadline:
                    raise SnmpTimeoutError(
                        f"SNMP WALK deadline exceeded "
                        f"({self._config.walk_timeout}s): "
                        f"{target.ip} prefix={prefix} "
                        f"({len(results)} OIDs collected before timeout)"
                    )

                try:
                    error_indication, error_status, error_index, var_bind_table = (
                        await asyncio.wait_for(
                            bulkCmd(
                                engine,
                                community,
                                transport,
                                context,
                                0,  # non-repeaters
                                max_rep,
                                ObjectType(current_oid),
                            ),
                            timeout=pdu_timeout,
                        )
                    )
                except asyncio.TimeoutError:
                    _pdu_hung = True
                    logger.warning(
                        "bulkCmd hung for %s (>%.0fs)",
                        target.ip, pdu_timeout,
                    )
                    raise SnmpTimeoutError(
                        f"SNMP bulkCmd hung: {target.ip} prefix={prefix} "
                        f"({len(results)} OIDs collected before hang)"
                    )

                if error_indication:
                    err_str = str(error_indication)
                    if "timeout" in err_str.lower():
                        raise SnmpTimeoutError(
                            f"SNMP WALK timeout: {target.ip} prefix={prefix}"
                        )
                    raise SnmpError(f"SNMP WALK error: {err_str}")

                if error_status:
                    raise SnmpError(
                        f"SNMP WALK error status: {error_status.prettyPrint()}"
                    )

                if not var_bind_table:
                    break

                out_of_scope = False
                for var_bind_row in var_bind_table:
                    if not var_bind_row:
                        out_of_scope = True
                        break
                    oid, val = var_bind_row[0]
                    oid_str = str(oid)

                    if not oid_str.startswith(prefix + "."):
                        out_of_scope = True
                        break

                    val_class = val.__class__.__name__
                    if val_class in (
                        "NoSuchObject", "NoSuchInstance", "EndOfMibView",
                    ):
                        out_of_scope = True
                        break

                    val_str = (
                        val.prettyPrint()
                        if hasattr(val, "prettyPrint")
                        else str(val)
                    )
                    results.append((oid_str, val_str))
                    current_oid = ObjectIdentity(oid_str)

                if out_of_scope or not var_bind_table:
                    break
        finally:
            if _pdu_hung:
                # Deferred close: let pending uvloop callbacks drain first
                self._deferred_close_engine(engine)
            else:
                self._close_engine(engine)

        return results
