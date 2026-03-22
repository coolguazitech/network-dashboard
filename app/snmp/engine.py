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


class SnmpError(Exception):
    """Base SNMP error."""


class SnmpTimeoutError(SnmpError):
    """SNMP request timed out after all retries."""


class SnmpNoSuchObjectError(SnmpError):
    """Requested OID does not exist on the device."""


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


class AsyncSnmpEngine:
    """
    Thin async wrapper around pysnmp-lextudio v6.x asyncio API.

    Thread-safe: uses a single shared pysnmp SnmpEngine instance.
    Auto-recovers by recreating the internal engine after accumulated errors.
    """

    _MAX_ERRORS_BEFORE_RESET = 3

    def __init__(self, config: SnmpEngineConfig | None = None) -> None:
        from pysnmp.hlapi.asyncio import SnmpEngine as PySnmpEngine

        self._config = config or SnmpEngineConfig()
        self._engine = PySnmpEngine()
        self._error_count = 0

    def _reset_engine(self) -> None:
        """Recreate internal pysnmp engine after corruption."""
        from pysnmp.hlapi.asyncio import SnmpEngine as PySnmpEngine

        old = self._engine
        try:
            if hasattr(old, "transportDispatcher"):
                old.transportDispatcher.closeDispatcher()
        except Exception:
            pass
        self._engine = PySnmpEngine()
        self._error_count = 0
        logger.warning("SNMP engine reset (recreated after %d errors)", self._MAX_ERRORS_BEFORE_RESET)

    def _make_transport(self, target: SnmpTarget) -> Any:
        """Create UDP transport for target (synchronous in v6)."""
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

        transport = self._make_transport(target)
        object_types = [
            ObjectType(ObjectIdentity(oid)) for oid in oids
        ]

        per_pdu_timeout = target.timeout * (target.retries + 1) + 5

        try:
            error_indication, error_status, error_index, var_binds = (
                await asyncio.wait_for(
                    getCmd(
                        self._engine,
                        CommunityData(target.community),
                        transport,
                        ContextData(),
                        *object_types,
                    ),
                    timeout=per_pdu_timeout,
                )
            )
        except asyncio.TimeoutError:
            logger.warning(
                "getCmd hung for %s (>%.0fs), resetting engine",
                target.ip, per_pdu_timeout,
            )
            self._reset_engine()
            raise SnmpTimeoutError(
                f"SNMP GET hung: {target.ip} OIDs={oids}"
            )

        if error_indication:
            err_str = str(error_indication)
            if "timeout" in err_str.lower() or "request" in err_str.lower():
                self._error_count += 1
                if self._error_count >= self._MAX_ERRORS_BEFORE_RESET:
                    self._reset_engine()
                raise SnmpTimeoutError(
                    f"SNMP GET timeout: {target.ip} OIDs={oids}"
                )
            raise SnmpError(f"SNMP GET error: {err_str}")

        if error_status:
            raise SnmpError(
                f"SNMP GET error status: {error_status.prettyPrint()} "
                f"at {var_binds[int(error_index) - 1][0] if error_index else '?'}"
            )

        self._error_count = 0
        result: dict[str, Any] = {}
        for oid, val in var_binds:
            oid_str = str(oid)
            val_str = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)

            # Check for noSuchObject / noSuchInstance / endOfMibView
            val_class = val.__class__.__name__
            if val_class in ("NoSuchObject", "NoSuchInstance", "EndOfMibView"):
                continue  # skip, don't raise — caller handles missing data

            result[oid_str] = val_str

        return result

    async def walk(
        self,
        target: SnmpTarget,
        oid_prefix: str,
        max_repetitions: int | None = None,
    ) -> list[tuple[str, str]]:
        """
        Full SNMP walk of a subtree using GETBULK.

        Uses an internal deadline instead of asyncio.wait_for to avoid
        cancelling the underlying pysnmp coroutine mid-flight, which can
        corrupt the shared SnmpEngine transport dispatcher state.

        Returns:
            List of (oid_str, value_str) tuples within the subtree.

        Raises:
            SnmpTimeoutError: if any GETBULK times out or walk exceeds deadline.
            SnmpError: on other errors.
        """
        try:
            result = await self._walk_impl(target, oid_prefix, max_repetitions)
            self._error_count = 0
            return result
        except SnmpTimeoutError:
            self._error_count += 1
            if self._error_count >= self._MAX_ERRORS_BEFORE_RESET:
                self._reset_engine()
            raise

    async def _walk_impl(
        self,
        target: SnmpTarget,
        oid_prefix: str,
        max_repetitions: int | None,
    ) -> list[tuple[str, str]]:
        """Internal walk implementation with deadline-based timeout."""
        from pysnmp.hlapi.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            bulkCmd,
        )

        max_rep = max_repetitions or self._config.max_repetitions
        transport = self._make_transport(target)
        results: list[tuple[str, str]] = []
        prefix = oid_prefix.rstrip(".")
        deadline = _time.monotonic() + self._config.walk_timeout

        # Start walking from the prefix
        current_oid = ObjectIdentity(prefix)
        community = CommunityData(target.community)
        context = ContextData()

        # Per-PDU hard timeout: pysnmp should respond within
        # timeout * (retries+1), but if it hangs (dispatcher bug),
        # wait_for will cancel it and we reset the engine.
        per_pdu_timeout = target.timeout * (target.retries + 1) + 5

        while True:
            # Check deadline before each GETBULK request
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
                            self._engine,
                            community,
                            transport,
                            context,
                            0,  # non-repeaters
                            max_rep,
                            ObjectType(current_oid),
                        ),
                        timeout=per_pdu_timeout,
                    )
                )
            except asyncio.TimeoutError:
                # bulkCmd hung — engine transport dispatcher is likely
                # corrupted by the cancellation, reset immediately.
                logger.warning(
                    "bulkCmd hung for %s (>%.0fs), resetting engine",
                    target.ip, per_pdu_timeout,
                )
                self._reset_engine()
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
                # bulkCmd returns 2-D table: each row is a list of ObjectType
                if not var_bind_row:
                    out_of_scope = True
                    break
                oid, val = var_bind_row[0]
                oid_str = str(oid)

                # Check if we've walked past our subtree
                if not oid_str.startswith(prefix + "."):
                    out_of_scope = True
                    break

                # Skip special values
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

        return results
