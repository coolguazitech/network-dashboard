"""
SNMP Collector — Power Supply Status.

HPE Comware: HH3C-ENTITY-EXT-MIB (entPhysicalClass=6 filter for power supplies).
Cisco IOS/NXOS: CISCO-ENVMON-MIB::ciscoEnvMonSupplyStatusTable.
"""
from __future__ import annotations

import logging

from app.core.enums import DeviceType
from app.parsers.protocols import ParsedData, PowerData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    CISCO_ENV_SUPPLY_DESCR,
    CISCO_ENV_SUPPLY_STATE,
    CISCO_ENVMON_STATE_MAP,
    ENT_PHYSICAL_CLASS,
    ENT_PHYSICAL_CLASS_POWER_SUPPLY,
    ENT_PHYSICAL_NAME,
    HH3C_ENTITY_EXT_ERROR_STATUS,
    HH3C_ERROR_STATUS_MAP,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class PowerCollector(BaseSnmpCollector):
    """Collect power supply status via SNMP."""

    api_name = "get_power"

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
        """HPE Comware: filter ENTITY-MIB by class=6 (powerSupply), read error status."""
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

        # Filter for power supply entities (class=6) and build results
        results: list[ParsedData] = []
        for idx, phys_class in class_map.items():
            if phys_class != ENT_PHYSICAL_CLASS_POWER_SUPPLY:
                continue

            error_code = error_map.get(idx)
            if error_code is None:
                continue

            status = HH3C_ERROR_STATUS_MAP.get(error_code, "unknown")
            ps_name = name_map.get(idx, f"PSU-{idx}")

            results.append(
                PowerData(ps_id=ps_name, status=status),
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
        """Cisco IOS/NXOS: CISCO-ENVMON-MIB supply status table."""
        state_varbinds = await engine.walk(target, CISCO_ENV_SUPPLY_STATE)
        descr_varbinds = await engine.walk(target, CISCO_ENV_SUPPLY_DESCR)

        # Build index -> description mapping
        descr_map: dict[str, str] = {}
        for oid_str, val_str in descr_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENV_SUPPLY_DESCR)
            descr_map[idx] = val_str

        results: list[ParsedData] = []
        for oid_str, val_str in state_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENV_SUPPLY_STATE)
            state_code = self.safe_int(val_str)
            status = CISCO_ENVMON_STATE_MAP.get(state_code, "unknown")
            ps_name = descr_map.get(idx, f"PSU-{idx}")

            results.append(
                PowerData(ps_id=ps_name, status=status),
            )

        all_varbinds = state_varbinds + descr_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
