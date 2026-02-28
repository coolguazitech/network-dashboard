"""
SNMP Collector — LLDP Neighbor Discovery (LLDP-MIB).

Walks lldpRemSysName, lldpRemPortId, lldpRemPortDesc to discover
remote neighbors. Also walks lldpLocPortDesc to map local port numbers
to interface names.

LLDP remote table index structure:
    lldpRemTimeMark.lldpRemLocalPortNum.lldpRemIndex

Output: NeighborData(local_interface, remote_hostname, remote_interface)
For remote_interface: prefers lldpRemPortDesc if non-empty, falls back
to lldpRemPortId.
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import NeighborData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    LLDP_LOC_PORT_DESC,
    LLDP_REM_PORT_DESC,
    LLDP_REM_PORT_ID,
    LLDP_REM_SYS_NAME,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class NeighborLldpCollector(BaseSnmpCollector):
    """Collect LLDP neighbor information via LLDP-MIB."""

    api_name = "get_uplink_lldp"

    @staticmethod
    def _parse_lldp_remote_index(oid_str: str, prefix: str) -> tuple[str, str, str] | None:
        """
        Parse LLDP remote table index from full OID.

        The index after the prefix is: {lldpRemTimeMark}.{lldpRemLocalPortNum}.{lldpRemIndex}

        Returns:
            (time_mark, local_port_num, rem_index) or None if parsing fails.
        """
        suffix = oid_str[len(prefix) + 1:]  # skip the dot after prefix
        parts = suffix.split(".")
        if len(parts) != 3:
            return None
        return parts[0], parts[1], parts[2]

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # Walk all needed LLDP OID trees
        rem_sys_name_varbinds = await engine.walk(target, LLDP_REM_SYS_NAME)
        rem_port_id_varbinds = await engine.walk(target, LLDP_REM_PORT_ID)
        rem_port_desc_varbinds = await engine.walk(target, LLDP_REM_PORT_DESC)
        loc_port_desc_varbinds = await engine.walk(target, LLDP_LOC_PORT_DESC)

        # Build local port number -> interface name mapping from lldpLocPortDesc
        # lldpLocPortDesc index: lldpLocPortNum
        local_port_map: dict[str, str] = {}
        for oid_str, val_str in loc_port_desc_varbinds:
            port_num = self.extract_index(oid_str, LLDP_LOC_PORT_DESC)
            if port_num and val_str:
                local_port_map[port_num] = val_str

        # Build keyed dictionaries for remote entries
        # Key = "{time_mark}.{local_port_num}.{rem_index}"
        def _make_key(parts: tuple[str, str, str]) -> str:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"

        rem_sys_names: dict[str, str] = {}
        rem_local_ports: dict[str, str] = {}  # key -> local_port_num
        for oid_str, val_str in rem_sys_name_varbinds:
            parsed = self._parse_lldp_remote_index(oid_str, LLDP_REM_SYS_NAME)
            if parsed:
                key = _make_key(parsed)
                rem_sys_names[key] = val_str
                rem_local_ports[key] = parsed[1]  # lldpRemLocalPortNum

        rem_port_ids: dict[str, str] = {}
        for oid_str, val_str in rem_port_id_varbinds:
            parsed = self._parse_lldp_remote_index(oid_str, LLDP_REM_PORT_ID)
            if parsed:
                rem_port_ids[_make_key(parsed)] = val_str

        rem_port_descs: dict[str, str] = {}
        for oid_str, val_str in rem_port_desc_varbinds:
            parsed = self._parse_lldp_remote_index(oid_str, LLDP_REM_PORT_DESC)
            if parsed:
                rem_port_descs[_make_key(parsed)] = val_str

        # Build results from remote sys name entries (primary key)
        results: list[ParsedData] = []
        for key, remote_hostname in rem_sys_names.items():
            if not remote_hostname:
                continue

            local_port_num = rem_local_ports.get(key, "")
            local_interface = local_port_map.get(local_port_num, f"port{local_port_num}")

            # Prefer lldpRemPortDesc, fallback to lldpRemPortId
            remote_port_desc = rem_port_descs.get(key, "")
            remote_port_id = rem_port_ids.get(key, "")
            remote_interface = remote_port_desc if remote_port_desc else remote_port_id

            if not remote_interface:
                logger.debug(
                    "LLDP: no remote interface for key %s on %s, skipping",
                    key, target.ip,
                )
                continue

            results.append(
                NeighborData(
                    local_interface=local_interface,
                    remote_hostname=remote_hostname,
                    remote_interface=remote_interface,
                )
            )

        all_varbinds = (
            rem_sys_name_varbinds
            + rem_port_id_varbinds
            + rem_port_desc_varbinds
            + loc_port_desc_varbinds
        )
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
