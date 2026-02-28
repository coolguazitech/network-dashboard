"""
SNMP Collector — MAC Address Table (Q-BRIDGE-MIB).

Walks dot1qTpFdbPort to collect MAC address table entries.

OID index structure encodes VLAN ID and MAC address:
    dot1qTpFdbPort.{vlan_id}.{mac_octet1}.{mac_octet2}.{mac_octet3}.{mac_octet4}.{mac_octet5}.{mac_octet6}

The value is a bridge port number, which must be converted via:
    bridge_port -> ifIndex (via session_cache.get_bridge_port_map())
    ifIndex -> ifName (via session_cache.get_ifindex_map())

MAC octets are extracted from the last 6 decimal OID components and
formatted as AA:BB:CC:DD:EE:FF.

Output: MacTableData(mac_address, interface_name, vlan_id)
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import MacTableData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import DOT1Q_TP_FDB_PORT
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


class MacTableCollector(BaseSnmpCollector):
    """Collect MAC address table via Q-BRIDGE-MIB::dot1qTpFdbPort."""

    api_name = "get_mac_table"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # Walk the Q-BRIDGE-MIB MAC table
        fdb_varbinds = await engine.walk(target, DOT1Q_TP_FDB_PORT)

        # Build mappings
        bridge_port_map = await session_cache.get_bridge_port_map(target.ip)
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        results: list[ParsedData] = []
        for oid_str, val_str in fdb_varbinds:
            # Extract the index portion after the OID prefix
            index_str = self.extract_index(oid_str, DOT1Q_TP_FDB_PORT)
            parsed = _parse_mac_index(index_str)
            if parsed is None:
                logger.debug(
                    "MAC table: failed to parse index '%s' on %s",
                    index_str, target.ip,
                )
                continue

            vlan_id, mac_address = parsed

            # Value is bridge port number
            bridge_port = self.safe_int(val_str, -1)
            if bridge_port < 0:
                continue

            # Convert bridge port -> ifIndex -> ifName
            ifindex = bridge_port_map.get(bridge_port)
            if ifindex is None:
                logger.debug(
                    "MAC table: no ifIndex for bridge port %d on %s",
                    bridge_port, target.ip,
                )
                continue

            ifname = ifindex_map.get(ifindex)
            if not ifname:
                logger.debug(
                    "MAC table: no ifName for ifIndex %d on %s",
                    ifindex, target.ip,
                )
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
