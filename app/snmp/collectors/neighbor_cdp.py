"""
SNMP Collector — CDP Neighbor Discovery (Cisco only).

Cisco IOS/NXOS: CISCO-CDP-MIB::cdpCacheTable.
HPE devices do not support CDP and return an empty list.
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import NeighborData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    CISCO_CDP_CACHE_DEVICE_ID,
    CISCO_CDP_CACHE_DEVICE_PORT,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class NeighborCdpCollector(BaseSnmpCollector):
    """Collect CDP neighbor information via SNMP (Cisco only)."""

    api_name = "get_uplink_cdp"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # HPE does not support CDP
        if device_type == DeviceType.HPE:
            raw_text = self.format_raw(
                self.api_name, target.ip, device_type, [],
            )
            return raw_text, []

        return await self._collect_cisco(
            target, device_type, session_cache, engine,
        )

    async def _collect_cisco(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """
        CISCO-CDP-MIB::cdpCacheTable.

        Index structure: cdpCacheIfIndex.cdpCacheDeviceIndex
        - cdpCacheIfIndex maps to IF-MIB ifIndex for the local interface.
        - cdpCacheDeviceIndex is an arbitrary per-interface sequence number.
        """
        device_id_varbinds = await engine.walk(
            target, CISCO_CDP_CACHE_DEVICE_ID,
        )
        device_port_varbinds = await engine.walk(
            target, CISCO_CDP_CACHE_DEVICE_PORT,
        )

        # Build {compound_index: remote_hostname}
        device_ids: dict[str, str] = {}
        for oid_str, val_str in device_id_varbinds:
            idx = self.extract_index(oid_str, CISCO_CDP_CACHE_DEVICE_ID)
            device_ids[idx] = val_str

        # Build {compound_index: remote_port}
        device_ports: dict[str, str] = {}
        for oid_str, val_str in device_port_varbinds:
            idx = self.extract_index(oid_str, CISCO_CDP_CACHE_DEVICE_PORT)
            device_ports[idx] = val_str

        # Map ifIndex -> ifName
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        results: list[ParsedData] = []
        for compound_idx in sorted(device_ids):
            remote_hostname = device_ids[compound_idx]
            remote_port = device_ports.get(compound_idx, "")

            # Extract cdpCacheIfIndex from compound index
            # compound_idx format: "{ifIndex}.{deviceIndex}"
            parts = compound_idx.split(".", 1)
            if not parts:
                continue
            if_index = self.safe_int(parts[0], -1)
            if if_index < 0:
                continue

            local_ifname = ifindex_map.get(if_index)
            if not local_ifname:
                logger.debug(
                    "CDP: no ifName for ifIndex %d on %s, skipping",
                    if_index, target.ip,
                )
                continue

            results.append(
                NeighborData(
                    local_interface=local_ifname,
                    remote_hostname=remote_hostname,
                    remote_interface=remote_port,
                ),
            )

        all_varbinds = device_id_varbinds + device_port_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
