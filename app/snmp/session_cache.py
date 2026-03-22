"""
SNMP Session Cache.

管理四種快取：
1. Community string cache — 記住每台設備用哪個 community（跨 round 共享）
2. Negative cache — SNMP 不通的設備冷卻期間不再嘗試（跨 round 共享）
3. Probe lock — 防止同一 IP 同時被多個 coroutine 探測（跨 round 共享）
4. ifIndex→ifName mapping — 每台設備建一次，同一 round 內共用
5. bridge port→ifIndex mapping — MAC table 專用，同一 round 內共用
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import TYPE_CHECKING, ClassVar

from app.snmp.engine import (
    AsyncSnmpEngine,
    SnmpError,
    SnmpTarget,
    SnmpTimeoutError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Standard MIB OIDs
_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
_IF_NAME_OID = "1.3.6.1.2.1.31.1.1.1.1"  # IF-MIB::ifName
_DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"  # BRIDGE-MIB

# Community probe uses shorter timeout than actual walks.
# A single sysObjectID GET should reply in <1s if SNMP is working.
_PROBE_TIMEOUT: float = 3.0
_PROBE_RETRIES: int = 1


class SnmpSessionCache:
    """
    Per-collection-cycle cache with shared cross-cycle community knowledge.

    Community cache (class-level): {ip: working_community}
      — Persists across job invocations. Once we know a device speaks
        community "public", we don't probe again next cycle.

    Negative cache (class-level): {ip: expiry_monotonic}
      — Devices where ALL communities failed. Skip for NEGATIVE_TTL seconds
        to avoid 50+ devices × 26s timeout blocking the entire semaphore pool.

    ifIndex/bridge caches (instance-level): rebuilt each collection cycle.
    """

    # ── Class-level shared state (survives across round invocations) ──
    _community_cache: ClassVar[dict[str, str]] = {}
    _negative_cache: ClassVar[dict[str, float]] = {}  # ip -> expiry monotonic
    _probe_locks: ClassVar[dict[str, asyncio.Lock]] = {}  # per-IP probe dedup
    NEGATIVE_TTL: ClassVar[float] = 300.0  # 5 min cooldown for SNMP-unreachable

    def __init__(
        self,
        engine: AsyncSnmpEngine,
        communities: list[str],
        port: int = 161,
        timeout: float = 5.0,
        retries: int = 2,
    ) -> None:
        self._engine = engine
        self._communities = communities
        self._port = port
        self._timeout = timeout
        self._retries = retries
        # Instance-level caches (per collection cycle)
        self._ifindex_cache: dict[str, dict[int, str]] = {}
        self._bridge_port_cache: dict[str, dict[int, int]] = {}

    async def get_target(self, ip: str) -> SnmpTarget:
        """
        Get an SnmpTarget with the correct community for this IP.

        1. Check class-level community cache (instant)
        2. Check negative cache — skip if recently failed (instant)
        3. Acquire per-IP lock (prevents duplicate probes from concurrent coroutines)
        4. Probe with fast timeout (3s × 1 retry per community)
        5. On success → cache community; on failure → add to negative cache
        """
        # 1. Known-good community (cached from any previous round)
        if ip in self._community_cache:
            return SnmpTarget(
                ip=ip,
                community=self._community_cache[ip],
                port=self._port,
                timeout=self._timeout,
                retries=self._retries,
            )

        # 2. Known-bad: recently failed all communities
        neg_expiry = self._negative_cache.get(ip)
        if neg_expiry is not None:
            if _time.monotonic() < neg_expiry:
                raise SnmpTimeoutError(
                    f"SNMP unreachable (cached, retry in "
                    f"{neg_expiry - _time.monotonic():.0f}s): {ip}"
                )
            # Cooldown expired, retry
            del self._negative_cache[ip]

        # 3. Per-IP lock — if another coroutine is already probing this IP,
        #    wait for it instead of sending duplicate SNMP probes.
        if ip not in self._probe_locks:
            self._probe_locks[ip] = asyncio.Lock()
        async with self._probe_locks[ip]:
            # Re-check caches after acquiring lock (another coroutine may
            # have populated them while we waited)
            if ip in self._community_cache:
                return SnmpTarget(
                    ip=ip,
                    community=self._community_cache[ip],
                    port=self._port,
                    timeout=self._timeout,
                    retries=self._retries,
                )
            neg_expiry = self._negative_cache.get(ip)
            if neg_expiry is not None and _time.monotonic() < neg_expiry:
                raise SnmpTimeoutError(
                    f"SNMP unreachable (cached, retry in "
                    f"{neg_expiry - _time.monotonic():.0f}s): {ip}"
                )

            # 4. Probe with FAST timeout (not the full walk timeout)
            for community in self._communities:
                probe_target = SnmpTarget(
                    ip=ip,
                    community=community,
                    port=self._port,
                    timeout=_PROBE_TIMEOUT,
                    retries=_PROBE_RETRIES,
                )
                try:
                    result = await self._engine.get(probe_target, _SYS_OBJECT_ID)
                    if result:
                        self._community_cache[ip] = community
                        logger.debug(
                            "Community for %s: %s", ip, community,
                        )
                        # Return target with FULL timeout for actual walks
                        return SnmpTarget(
                            ip=ip,
                            community=community,
                            port=self._port,
                            timeout=self._timeout,
                            retries=self._retries,
                        )
                except SnmpTimeoutError:
                    logger.debug(
                        "Community '%s' timed out for %s, trying next",
                        community, ip,
                    )
                    continue
                except SnmpError as e:
                    logger.debug(
                        "Community '%s' failed for %s: %s, trying next",
                        community, ip, e,
                    )
                    continue

            # 5. All communities failed → negative cache
            self._negative_cache[ip] = _time.monotonic() + self.NEGATIVE_TTL
            logger.info(
                "SNMP unreachable: %s (all communities failed, "
                "skipping for %ds)",
                ip, int(self.NEGATIVE_TTL),
            )
            raise SnmpTimeoutError(
                f"All communities failed for {ip}: "
                f"tried {self._communities}"
            )

    async def get_ifindex_map(self, ip: str) -> dict[int, str]:
        """
        Get ifIndex→ifName mapping for a device.

        Walks IF-MIB::ifName once, caches result for the cycle.
        """
        if ip in self._ifindex_cache:
            return self._ifindex_cache[ip]

        target = await self.get_target(ip)
        varbinds = await self._engine.walk(target, _IF_NAME_OID)

        ifindex_map: dict[int, str] = {}
        for oid_str, val_str in varbinds:
            # OID format: 1.3.6.1.2.1.31.1.1.1.1.{ifIndex}
            try:
                ifindex = int(oid_str.rsplit(".", 1)[-1])
                ifindex_map[ifindex] = val_str
            except (ValueError, IndexError):
                continue

        self._ifindex_cache[ip] = ifindex_map
        logger.debug(
            "Built ifIndex map for %s: %d interfaces", ip, len(ifindex_map),
        )
        return ifindex_map

    async def get_bridge_port_map(self, ip: str) -> dict[int, int]:
        """
        Get bridge port→ifIndex mapping for a device.

        Walks BRIDGE-MIB::dot1dBasePortIfIndex once, caches result.
        Needed by MAC table collector to convert bridge port numbers
        to ifIndex values.
        """
        if ip in self._bridge_port_cache:
            return self._bridge_port_cache[ip]

        target = await self.get_target(ip)
        varbinds = await self._engine.walk(
            target, _DOT1D_BASE_PORT_IF_INDEX,
        )

        bridge_map: dict[int, int] = {}
        for oid_str, val_str in varbinds:
            # OID: ...17.1.4.1.2.{bridge_port} = {ifIndex}
            try:
                bridge_port = int(oid_str.rsplit(".", 1)[-1])
                ifindex = int(val_str)
                bridge_map[bridge_port] = ifindex
            except (ValueError, IndexError):
                continue

        self._bridge_port_cache[ip] = bridge_map
        logger.debug(
            "Built bridge port map for %s: %d ports", ip, len(bridge_map),
        )
        return bridge_map

    def clear(self) -> None:
        """Clear instance-level caches (call at start of each collection cycle).

        NOTE: community_cache and negative_cache are class-level
        and intentionally NOT cleared here.
        """
        self._ifindex_cache.clear()
        self._bridge_port_cache.clear()

    @classmethod
    def clear_all(cls) -> None:
        """Clear all caches including class-level (for testing/reset)."""
        cls._community_cache.clear()
        cls._negative_cache.clear()
        cls._probe_locks.clear()
