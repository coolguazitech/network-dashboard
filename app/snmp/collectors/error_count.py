"""
SNMP Collector — Interface Error Count (IF-MIB).

Walks ifInErrors + ifOutErrors, maps ifIndex to ifName via session_cache,
and returns InterfaceErrorData with combined CRC error counts.
Only includes interfaces where total errors > 0.
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import InterfaceErrorData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import IF_IN_ERRORS, IF_OUT_ERRORS
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class ErrorCountCollector(BaseSnmpCollector):
    """Collect interface error counts via IF-MIB::ifInErrors / ifOutErrors."""

    api_name = "get_error_count"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # Walk both error OID trees
        in_errors_varbinds = await engine.walk(target, IF_IN_ERRORS)
        out_errors_varbinds = await engine.walk(target, IF_OUT_ERRORS)

        # Build ifIndex -> ifName mapping
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # Index in-errors by ifIndex
        in_errors: dict[int, int] = {}
        for oid_str, val_str in in_errors_varbinds:
            idx_str = self.extract_index(oid_str, IF_IN_ERRORS)
            ifindex = self.safe_int(idx_str, -1)
            if ifindex >= 0:
                in_errors[ifindex] = self.safe_int(val_str)

        # Index out-errors by ifIndex
        out_errors: dict[int, int] = {}
        for oid_str, val_str in out_errors_varbinds:
            idx_str = self.extract_index(oid_str, IF_OUT_ERRORS)
            ifindex = self.safe_int(idx_str, -1)
            if ifindex >= 0:
                out_errors[ifindex] = self.safe_int(val_str)

        # Combine and filter
        all_varbinds = in_errors_varbinds + out_errors_varbinds
        all_ifindexes = set(in_errors.keys()) | set(out_errors.keys())

        results: list[ParsedData] = []
        for ifindex in sorted(all_ifindexes):
            total = in_errors.get(ifindex, 0) + out_errors.get(ifindex, 0)
            if total <= 0:
                continue

            ifname = ifindex_map.get(ifindex)
            if not ifname:
                logger.debug(
                    "ErrorCount: no ifName for ifIndex %d on %s, skipping",
                    ifindex, target.ip,
                )
                continue

            results.append(
                InterfaceErrorData(
                    interface_name=ifname,
                    crc_errors=total,
                )
            )

        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
