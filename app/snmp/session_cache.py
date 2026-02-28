"""
SNMP Session Cache.

管理兩種快取：
1. Community string cache — 記住每台設備用哪個 community
2. ifIndex→ifName mapping — 每台設備建一次，所有 collector 共用
3. bridge port→ifIndex mapping — MAC table 專用
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


class SnmpSessionCache:
    """
    Per-collection-cycle cache.

    Community cache: {ip: working_community}
    ifIndex cache:   {ip: {ifIndex: ifName}}
    bridge port cache: {ip: {bridge_port: ifIndex}}
    """

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
        self._community_cache: dict[str, str] = {}
        self._ifindex_cache: dict[str, dict[int, str]] = {}
        self._bridge_port_cache: dict[str, dict[int, int]] = {}

    async def get_target(self, ip: str) -> SnmpTarget:
        """
        Get an SnmpTarget with the correct community for this IP.

        Probes with sysObjectID.0 GET, trying each community in order.
        Caches the first successful community.
        """
        if ip in self._community_cache:
            return SnmpTarget(
                ip=ip,
                community=self._community_cache[ip],
                port=self._port,
                timeout=self._timeout,
                retries=self._retries,
            )

        for community in self._communities:
            target = SnmpTarget(
                ip=ip,
                community=community,
                port=self._port,
                timeout=self._timeout,
                retries=self._retries,
            )
            try:
                result = await self._engine.get(target, _SYS_OBJECT_ID)
                if result:
                    self._community_cache[ip] = community
                    logger.debug(
                        "Community for %s: %s", ip, community,
                    )
                    return target
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
        """Clear all caches (call at start of each collection cycle)."""
        self._community_cache.clear()
        self._ifindex_cache.clear()
        self._bridge_port_cache.clear()
