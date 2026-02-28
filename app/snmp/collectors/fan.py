"""
SNMP Collector — Fan Status.

HPE Comware: HH3C-ENTITY-EXT-MIB (entPhysicalClass=7 filter for fans).
Cisco IOS/NXOS: CISCO-ENVMON-MIB::ciscoEnvMonFanStatusTable.
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import FanStatusData, ParsedData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    CISCO_ENV_FAN_DESCR,
    CISCO_ENV_FAN_STATE,
    CISCO_ENVMON_STATE_MAP,
    ENT_PHYSICAL_CLASS,
    ENT_PHYSICAL_CLASS_FAN,
    ENT_PHYSICAL_NAME,
    HH3C_ENTITY_EXT_ERROR_STATUS,
    HH3C_ERROR_STATUS_MAP,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class FanCollector(BaseSnmpCollector):
    """Collect fan status via SNMP."""

    api_name = "get_fan"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        if device_type == DeviceType.HPE:
            return await self._collect_hpe(target, device_type, engine)
        else:
            # Cisco IOS / NXOS
            return await self._collect_cisco(target, device_type, engine)

    async def _collect_hpe(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """HPE Comware: filter ENTITY-MIB by class=7 (fan), read error status."""
        error_varbinds = await engine.walk(target, HH3C_ENTITY_EXT_ERROR_STATUS)
        class_varbinds = await engine.walk(target, ENT_PHYSICAL_CLASS)
        name_varbinds = await engine.walk(target, ENT_PHYSICAL_NAME)

        # Build index -> class mapping
        class_map: dict[str, int] = {}
        for oid_str, val_str in class_varbinds:
            idx = self.extract_index(oid_str, ENT_PHYSICAL_CLASS)
            class_map[idx] = self.safe_int(val_str)

        # Build index -> name mapping
        name_map: dict[str, str] = {}
        for oid_str, val_str in name_varbinds:
            idx = self.extract_index(oid_str, ENT_PHYSICAL_NAME)
            name_map[idx] = val_str

        # Build index -> error status mapping
        error_map: dict[str, int] = {}
        for oid_str, val_str in error_varbinds:
            idx = self.extract_index(oid_str, HH3C_ENTITY_EXT_ERROR_STATUS)
            error_map[idx] = self.safe_int(val_str)

        # Filter for fan entities (class=7) and build results
        results: list[ParsedData] = []
        for idx, phys_class in class_map.items():
            if phys_class != ENT_PHYSICAL_CLASS_FAN:
                continue

            error_code = error_map.get(idx)
            if error_code is None:
                continue

            status = HH3C_ERROR_STATUS_MAP.get(error_code, "unknown")
            fan_name = name_map.get(idx, f"Fan-{idx}")

            results.append(
                FanStatusData(fan_id=fan_name, status=status),
            )

        all_varbinds = error_varbinds + class_varbinds + name_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results

    async def _collect_cisco(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """Cisco IOS/NXOS: CISCO-ENVMON-MIB fan status table."""
        state_varbinds = await engine.walk(target, CISCO_ENV_FAN_STATE)
        descr_varbinds = await engine.walk(target, CISCO_ENV_FAN_DESCR)

        # Build index -> description mapping
        descr_map: dict[str, str] = {}
        for oid_str, val_str in descr_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENV_FAN_DESCR)
            descr_map[idx] = val_str

        results: list[ParsedData] = []
        for oid_str, val_str in state_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENV_FAN_STATE)
            state_code = self.safe_int(val_str)
            status = CISCO_ENVMON_STATE_MAP.get(state_code, "unknown")
            fan_name = descr_map.get(idx, f"Fan-{idx}")

            results.append(
                FanStatusData(fan_id=fan_name, status=status),
            )

        all_varbinds = state_varbinds + descr_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
