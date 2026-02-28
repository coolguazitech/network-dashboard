"""
SNMP Collector — Interface Status (IF-MIB + EtherLike-MIB).

Walks ifOperStatus, ifHighSpeed, and dot3StatsDuplexStatus to determine
interface link status, speed, and duplex mode. Maps ifIndex to ifName
via session_cache.

Only includes physical Ethernet interfaces (filters out loopback, VLAN,
Null, and other non-physical interface types by checking ifName prefix).

Speed conversion from ifHighSpeed (Mbps):
    10 -> "10M", 100 -> "100M", 1000 -> "1G", 10000 -> "10G",
    40000 -> "40G", 100000 -> "100G"
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import InterfaceStatusData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    DOT3_STATS_DUPLEX,
    DUPLEX_STATUS_MAP,
    IF_HIGH_SPEED,
    IF_OPER_STATUS,
    IF_OPER_STATUS_MAP,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)

# Prefixes of non-physical interfaces to skip
_SKIP_PREFIXES = (
    "Loopback", "Lo",
    "Vlan", "Vl",
    "Null", "Nu",
    "Tunnel", "Tu",
    "mgmt", "Management",
    "Cpu", "cpu",
    "Stack", "InLoopBack",
    "Register", "Aux",
)

# Speed mapping: ifHighSpeed (Mbps) -> display string
_SPEED_MAP: dict[int, str] = {
    10: "10M",
    100: "100M",
    1000: "1G",
    2500: "2.5G",
    5000: "5G",
    10000: "10G",
    25000: "25G",
    40000: "40G",
    50000: "50G",
    100000: "100G",
}


def _format_speed(mbps: int) -> str:
    """Convert ifHighSpeed Mbps value to human-readable speed string."""
    if mbps in _SPEED_MAP:
        return _SPEED_MAP[mbps]
    if mbps >= 1000:
        return f"{mbps // 1000}G"
    if mbps > 0:
        return f"{mbps}M"
    return "unknown"


class InterfaceStatusCollector(BaseSnmpCollector):
    """Collect interface status via IF-MIB and EtherLike-MIB."""

    api_name = "get_interface_status"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # Walk the three OID trees
        oper_status_varbinds = await engine.walk(target, IF_OPER_STATUS)
        high_speed_varbinds = await engine.walk(target, IF_HIGH_SPEED)
        duplex_varbinds = await engine.walk(target, DOT3_STATS_DUPLEX)

        # Build ifIndex -> ifName mapping
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # Index oper status by ifIndex
        oper_status_by_idx: dict[int, int] = {}
        for oid_str, val_str in oper_status_varbinds:
            idx_str = self.extract_index(oid_str, IF_OPER_STATUS)
            ifindex = self.safe_int(idx_str, -1)
            if ifindex >= 0:
                oper_status_by_idx[ifindex] = self.safe_int(val_str)

        # Index high speed by ifIndex
        high_speed_by_idx: dict[int, int] = {}
        for oid_str, val_str in high_speed_varbinds:
            idx_str = self.extract_index(oid_str, IF_HIGH_SPEED)
            ifindex = self.safe_int(idx_str, -1)
            if ifindex >= 0:
                high_speed_by_idx[ifindex] = self.safe_int(val_str)

        # Index duplex by ifIndex
        duplex_by_idx: dict[int, int] = {}
        for oid_str, val_str in duplex_varbinds:
            idx_str = self.extract_index(oid_str, DOT3_STATS_DUPLEX)
            ifindex = self.safe_int(idx_str, -1)
            if ifindex >= 0:
                duplex_by_idx[ifindex] = self.safe_int(val_str)

        # Build results for physical Ethernet interfaces only
        results: list[ParsedData] = []
        for ifindex in sorted(oper_status_by_idx.keys()):
            ifname = ifindex_map.get(ifindex)
            if not ifname:
                continue

            # Skip non-physical interfaces
            if ifname.startswith(_SKIP_PREFIXES):
                continue

            # Link status
            oper_val = oper_status_by_idx[ifindex]
            link_status = IF_OPER_STATUS_MAP.get(oper_val, "unknown")

            # Speed
            speed_mbps = high_speed_by_idx.get(ifindex, 0)
            speed = _format_speed(speed_mbps)

            # Duplex
            duplex_val = duplex_by_idx.get(ifindex)
            duplex = DUPLEX_STATUS_MAP.get(duplex_val, "unknown") if duplex_val is not None else None

            results.append(
                InterfaceStatusData(
                    interface_name=ifname,
                    link_status=link_status,
                    speed=speed,
                    duplex=duplex,
                )
            )

        all_varbinds = oper_status_varbinds + high_speed_varbinds + duplex_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
