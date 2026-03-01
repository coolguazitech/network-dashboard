"""
SNMP Collector — MAC Address Table.

Two modes depending on device type:

1. HPE / Cisco-NXOS (standard Q-BRIDGE-MIB):
   Walk dot1qTpFdbPort — index encodes VLAN + MAC:
     dot1qTpFdbPort.{vlan_id}.{o1}.{o2}.{o3}.{o4}.{o5}.{o6} = bridge_port

2. Cisco-IOS (per-VLAN community indexing):
   a) Walk VTP VLAN list to find active VLANs
   b) For each VLAN, use community@vlanID to walk BRIDGE-MIB::dot1dTpFdbPort
      Index is 6 MAC octets only (VLAN implied by context):
        dot1dTpFdbPort.{o1}.{o2}.{o3}.{o4}.{o5}.{o6} = bridge_port
   c) Bridge port map also walked per-VLAN context

Output: MacTableData(mac_address, interface_name, vlan_id)
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import MacTableData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget, SnmpTimeoutError
from app.snmp.oid_maps import (
    CISCO_VTP_VLAN_STATE,
    DOT1D_BASE_PORT_IF_INDEX,
    DOT1D_TP_FDB_PORT,
    DOT1Q_TP_FDB_PORT,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


def _parse_mac_index(index_str: str) -> tuple[int, str] | None:
    """
    Parse the dot1qTpFdbPort index into (vlan_id, mac_address).

    Index format: {vlan_id}.{o1}.{o2}.{o3}.{o4}.{o5}.{o6}
    where o1-o6 are decimal MAC octets.

    Returns:
        (vlan_id, "AA:BB:CC:DD:EE:FF") or None if parsing fails.
    """
    parts = index_str.split(".")
    if len(parts) != 7:
        return None
    try:
        vlan_id = int(parts[0])
        octets = [int(p) for p in parts[1:7]]
    except (ValueError, IndexError):
        return None

    # Validate octet range
    if any(o < 0 or o > 255 for o in octets):
        return None

    mac_address = ":".join(f"{o:02X}" for o in octets)
    return vlan_id, mac_address


def _parse_bridge_mac_index(index_str: str) -> str | None:
    """
    Parse BRIDGE-MIB dot1dTpFdbPort index into MAC address.

    Index format: {o1}.{o2}.{o3}.{o4}.{o5}.{o6}
    (no VLAN prefix — VLAN is implicit from community@vlanID context)
    """
    parts = index_str.split(".")
    if len(parts) != 6:
        return None
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return None

    if any(o < 0 or o > 255 for o in octets):
        return None

    return ":".join(f"{o:02X}" for o in octets)


class MacTableCollector(BaseSnmpCollector):
    """Collect MAC address table via Q-BRIDGE-MIB or per-VLAN BRIDGE-MIB."""

    api_name = "get_mac_table"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        if device_type == DeviceType.CISCO_IOS:
            return await self._collect_cisco_ios(
                target, device_type, session_cache, engine,
            )
        return await self._collect_standard(
            target, device_type, session_cache, engine,
        )

    async def _collect_standard(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """HPE / Cisco-NXOS: standard Q-BRIDGE-MIB walk."""
        fdb_varbinds = await engine.walk(target, DOT1Q_TP_FDB_PORT)

        bridge_port_map = await session_cache.get_bridge_port_map(target.ip)
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        results: list[ParsedData] = []
        for oid_str, val_str in fdb_varbinds:
            index_str = self.extract_index(oid_str, DOT1Q_TP_FDB_PORT)
            parsed = _parse_mac_index(index_str)
            if parsed is None:
                logger.debug(
                    "MAC table: failed to parse index '%s' on %s",
                    index_str, target.ip,
                )
                continue

            vlan_id, mac_address = parsed
            bridge_port = self.safe_int(val_str, -1)
            if bridge_port < 0:
                continue

            ifindex = bridge_port_map.get(bridge_port)
            if ifindex is None:
                continue

            ifname = ifindex_map.get(ifindex)
            if not ifname:
                continue

            results.append(
                MacTableData(
                    mac_address=mac_address,
                    interface_name=ifname,
                    vlan_id=vlan_id,
                )
            )

        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, fdb_varbinds,
        )
        return raw_text, results

    async def _collect_cisco_ios(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """Cisco IOS: per-VLAN community indexing (community@vlanID)."""
        # 1. Walk VTP VLAN list to get active VLANs
        vlans = await self._get_active_vlans(target, engine)
        if not vlans:
            logger.warning(
                "MAC table: no active VLANs found on %s, "
                "falling back to standard Q-BRIDGE",
                target.ip,
            )
            return await self._collect_standard(
                target, device_type, session_cache, engine,
            )

        # 2. ifIndex map is global (not per-VLAN)
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # 3. Walk each VLAN with community@vlanID
        all_fdb_varbinds: list[tuple[str, str]] = []
        results: list[ParsedData] = []

        for vlan_id in vlans:
            vlan_target = SnmpTarget(
                ip=target.ip,
                community=f"{target.community}@{vlan_id}",
                port=target.port,
                timeout=target.timeout,
                retries=target.retries,
            )

            try:
                vlan_results = await self._walk_vlan_mac_table(
                    vlan_target, vlan_id, ifindex_map, engine,
                    all_fdb_varbinds,
                )
                results.extend(vlan_results)
            except SnmpTimeoutError:
                logger.debug(
                    "MAC table: VLAN %d timed out on %s, skipping",
                    vlan_id, target.ip,
                )
                continue

        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_fdb_varbinds,
        )
        return raw_text, results

    async def _get_active_vlans(
        self,
        target: SnmpTarget,
        engine: AsyncSnmpEngine,
    ) -> list[int]:
        """Walk CISCO-VTP-MIB::vtpVlanState to get active VLAN IDs."""
        vtp_varbinds = await engine.walk(target, CISCO_VTP_VLAN_STATE)

        vlans: list[int] = []
        for oid_str, val_str in vtp_varbinds:
            # OID: ...vtpVlanState.{domain}.{vlanID}
            # Value: 1=operational, 2=suspended, ...
            if val_str != "1":
                continue

            # Extract VLAN ID (last OID component)
            try:
                vlan_id = int(oid_str.rsplit(".", 1)[-1])
            except (ValueError, IndexError):
                continue

            # Skip Cisco reserved VLANs (1002-1005: fddi, token-ring, etc.)
            if 1002 <= vlan_id <= 1005:
                continue

            vlans.append(vlan_id)

        logger.debug(
            "Cisco IOS VLANs on %s: %s", target.ip, vlans,
        )
        return vlans

    async def _walk_vlan_mac_table(
        self,
        vlan_target: SnmpTarget,
        vlan_id: int,
        ifindex_map: dict[int, str],
        engine: AsyncSnmpEngine,
        all_fdb_varbinds: list[tuple[str, str]],
    ) -> list[ParsedData]:
        """Walk BRIDGE-MIB MAC table for a single VLAN context."""
        # Walk bridge port map per-VLAN (it differs per VLAN on IOS)
        bridge_varbinds = await engine.walk(
            vlan_target, DOT1D_BASE_PORT_IF_INDEX,
        )
        bridge_port_map: dict[int, int] = {}
        for oid_str, val_str in bridge_varbinds:
            try:
                bp = int(oid_str.rsplit(".", 1)[-1])
                ifidx = int(val_str)
                bridge_port_map[bp] = ifidx
            except (ValueError, IndexError):
                continue

        # Walk BRIDGE-MIB::dot1dTpFdbPort
        fdb_varbinds = await engine.walk(vlan_target, DOT1D_TP_FDB_PORT)
        all_fdb_varbinds.extend(fdb_varbinds)

        results: list[ParsedData] = []
        for oid_str, val_str in fdb_varbinds:
            index_str = self.extract_index(oid_str, DOT1D_TP_FDB_PORT)
            mac_address = _parse_bridge_mac_index(index_str)
            if mac_address is None:
                logger.debug(
                    "MAC table: failed to parse bridge index '%s' "
                    "on %s VLAN %d",
                    index_str, vlan_target.ip, vlan_id,
                )
                continue

            bridge_port = self.safe_int(val_str, -1)
            if bridge_port < 0:
                continue

            ifindex = bridge_port_map.get(bridge_port)
            if ifindex is None:
                continue

            ifname = ifindex_map.get(ifindex)
            if not ifname:
                continue

            results.append(
                MacTableData(
                    mac_address=mac_address,
                    interface_name=ifname,
                    vlan_id=vlan_id,
                )
            )

        return results
