"""
SNMP Collector — Transceiver (SFP/QSFP) DOM diagnostics.

HPE Comware: HH3C-TRANSCEIVER-INFO-MIB (temperature, voltage, tx/rx power per ifIndex).
Cisco IOS/NXOS: CISCO-ENTITY-SENSOR-MIB + ENTITY-MIB cross-reference.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from app.core.enums import DeviceType
from app.parsers.protocols import (
    ParsedData,
    TransceiverChannelData,
    TransceiverData,
)
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    CISCO_ENT_SENSOR_PRECISION,
    CISCO_ENT_SENSOR_SCALE,
    CISCO_ENT_SENSOR_TYPE,
    CISCO_ENT_SENSOR_VALUE,
    CISCO_SENSOR_SCALE_MAP,
    CISCO_SENSOR_TYPE_CELSIUS,
    CISCO_SENSOR_TYPE_DBM,
    CISCO_SENSOR_TYPE_VOLTS_DC,
    ENT_PHYSICAL_NAME,
    HH3C_TRANSCEIVER_RX_POWER,
    HH3C_TRANSCEIVER_TEMPERATURE,
    HH3C_TRANSCEIVER_TX_POWER,
    HH3C_TRANSCEIVER_VOLTAGE,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)

# ENTITY-MIB::entPhysicalContainedIn — not in oid_maps, define locally.
_ENT_PHYSICAL_CONTAINED_IN = "1.3.6.1.2.1.47.1.1.1.1.4"


class TransceiverCollector(BaseSnmpCollector):
    """Collect transceiver DOM data via SNMP."""

    api_name = "get_gbic_details"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        if device_type == DeviceType.HPE:
            return await self._collect_hpe(
                target, device_type, session_cache, engine,
            )
        else:
            return await self._collect_cisco(
                target, device_type, session_cache, engine,
            )

    # ── HPE Comware ─────────────────────────────────────────────────

    async def _collect_hpe(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """
        HH3C-TRANSCEIVER-INFO-MIB: indexed by ifIndex.

        Values:
        - temperature: 1 degree C units
        - voltage: millivolts (0.001 V)
        - tx_power / rx_power: 0.01 dBm
        """
        temp_varbinds = await engine.walk(target, HH3C_TRANSCEIVER_TEMPERATURE)
        volt_varbinds = await engine.walk(target, HH3C_TRANSCEIVER_VOLTAGE)
        tx_varbinds = await engine.walk(target, HH3C_TRANSCEIVER_TX_POWER)
        rx_varbinds = await engine.walk(target, HH3C_TRANSCEIVER_RX_POWER)

        # Map ifIndex -> ifName
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # Build per-ifIndex value dicts
        temps: dict[int, float] = {}
        for oid_str, val_str in temp_varbinds:
            idx = self.safe_int(
                self.extract_index(oid_str, HH3C_TRANSCEIVER_TEMPERATURE), -1,
            )
            if idx >= 0:
                temps[idx] = float(self.safe_int(val_str))  # 1 degree C

        volts: dict[int, float] = {}
        for oid_str, val_str in volt_varbinds:
            idx = self.safe_int(
                self.extract_index(oid_str, HH3C_TRANSCEIVER_VOLTAGE), -1,
            )
            if idx >= 0:
                volts[idx] = self.safe_int(val_str) / 100.0  # 0.01V -> V

        tx_powers: dict[int, float] = {}
        for oid_str, val_str in tx_varbinds:
            idx = self.safe_int(
                self.extract_index(oid_str, HH3C_TRANSCEIVER_TX_POWER), -1,
            )
            if idx >= 0:
                tx_powers[idx] = self.safe_int(val_str) / 100.0  # 0.01 dBm -> dBm

        rx_powers: dict[int, float] = {}
        for oid_str, val_str in rx_varbinds:
            idx = self.safe_int(
                self.extract_index(oid_str, HH3C_TRANSCEIVER_RX_POWER), -1,
            )
            if idx >= 0:
                rx_powers[idx] = self.safe_int(val_str) / 100.0  # 0.01 dBm -> dBm

        # Build results: one TransceiverData per ifIndex with data
        all_ifindexes = set(temps) | set(volts) | set(tx_powers) | set(rx_powers)

        results: list[ParsedData] = []
        for ifindex in sorted(all_ifindexes):
            ifname = ifindex_map.get(ifindex)
            if not ifname:
                logger.debug(
                    "Transceiver: no ifName for ifIndex %d on %s, skipping",
                    ifindex, target.ip,
                )
                continue

            temperature = temps.get(ifindex)
            voltage = volts.get(ifindex)
            tx_pwr = tx_powers.get(ifindex)
            rx_pwr = rx_powers.get(ifindex)

            # Single channel (SFP) per interface
            channels = [
                TransceiverChannelData(
                    channel=1,
                    tx_power=tx_pwr,
                    rx_power=rx_pwr,
                ),
            ]

            results.append(
                TransceiverData(
                    interface_name=ifname,
                    temperature=temperature,
                    voltage=voltage,
                    channels=channels,
                ),
            )

        all_varbinds = temp_varbinds + volt_varbinds + tx_varbinds + rx_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results

    # ── Cisco IOS / NXOS ────────────────────────────────────────────

    async def _collect_cisco(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        """
        CISCO-ENTITY-SENSOR-MIB + ENTITY-MIB.

        Steps:
        1. Walk sensor value/type/scale/precision tables.
        2. Walk entPhysicalName for interface names.
        3. Walk entPhysicalContainedIn to map sensor -> parent entity.
        4. Filter sensors by type (celsius, voltsDC, dBm).
        5. Compute actual_value = sensor_value * scale_factor * 10^(-precision).
        6. Group by parent interface and build TransceiverData.
        """
        value_varbinds = await engine.walk(target, CISCO_ENT_SENSOR_VALUE)
        type_varbinds = await engine.walk(target, CISCO_ENT_SENSOR_TYPE)
        scale_varbinds = await engine.walk(target, CISCO_ENT_SENSOR_SCALE)
        prec_varbinds = await engine.walk(target, CISCO_ENT_SENSOR_PRECISION)
        name_varbinds = await engine.walk(target, ENT_PHYSICAL_NAME)
        contained_varbinds = await engine.walk(target, _ENT_PHYSICAL_CONTAINED_IN)

        # Build entity index -> sensor value
        sensor_values: dict[str, int] = {}
        for oid_str, val_str in value_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENT_SENSOR_VALUE)
            sensor_values[idx] = self.safe_int(val_str)

        # Build entity index -> sensor type
        sensor_types: dict[str, int] = {}
        for oid_str, val_str in type_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENT_SENSOR_TYPE)
            sensor_types[idx] = self.safe_int(val_str)

        # Build entity index -> sensor scale
        sensor_scales: dict[str, int] = {}
        for oid_str, val_str in scale_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENT_SENSOR_SCALE)
            sensor_scales[idx] = self.safe_int(val_str)

        # Build entity index -> sensor precision
        sensor_precisions: dict[str, int] = {}
        for oid_str, val_str in prec_varbinds:
            idx = self.extract_index(oid_str, CISCO_ENT_SENSOR_PRECISION)
            sensor_precisions[idx] = self.safe_int(val_str)

        # Build entity index -> physical name
        entity_names: dict[str, str] = {}
        for oid_str, val_str in name_varbinds:
            idx = self.extract_index(oid_str, ENT_PHYSICAL_NAME)
            entity_names[idx] = val_str

        # Build entity index -> parent entity index (containedIn)
        contained_in: dict[str, str] = {}
        for oid_str, val_str in contained_varbinds:
            idx = self.extract_index(oid_str, _ENT_PHYSICAL_CONTAINED_IN)
            contained_in[idx] = val_str

        # Filter relevant sensors and compute actual values
        # Group by parent interface: {parent_idx: {sensor_type: actual_value, ...}}
        # For dBm sensors, we collect them separately to handle tx/rx
        _RELEVANT_TYPES = {
            CISCO_SENSOR_TYPE_CELSIUS,
            CISCO_SENSOR_TYPE_VOLTS_DC,
            CISCO_SENSOR_TYPE_DBM,
        }

        # parent_idx -> list of (sensor_type, actual_value, sensor_name)
        parent_sensors: dict[str, list[tuple[int, float, str]]] = defaultdict(list)

        for idx in sensor_values:
            s_type = sensor_types.get(idx)
            if s_type not in _RELEVANT_TYPES:
                continue

            raw_val = sensor_values[idx]
            scale_code = sensor_scales.get(idx, 9)  # default: units
            precision = sensor_precisions.get(idx, 0)
            scale_factor = CISCO_SENSOR_SCALE_MAP.get(scale_code, 1.0)
            actual_value = raw_val * scale_factor * (10 ** (-precision))

            # Walk up containment to find parent interface
            parent_idx = contained_in.get(idx, idx)
            sensor_name = entity_names.get(idx, "")

            parent_sensors[parent_idx].append(
                (s_type, actual_value, sensor_name),
            )

        # Build TransceiverData per parent entity
        results: list[ParsedData] = []
        for parent_idx in sorted(parent_sensors):
            iface_name = entity_names.get(parent_idx, "")
            if not iface_name:
                # Try to walk further up to find a named parent
                grandparent = contained_in.get(parent_idx, "")
                iface_name = entity_names.get(grandparent, f"Entity-{parent_idx}")

            sensors = parent_sensors[parent_idx]

            temperature: float | None = None
            voltage: float | None = None
            tx_powers: list[float] = []
            rx_powers: list[float] = []

            for s_type, actual_val, s_name in sensors:
                if s_type == CISCO_SENSOR_TYPE_CELSIUS:
                    temperature = actual_val
                elif s_type == CISCO_SENSOR_TYPE_VOLTS_DC:
                    voltage = actual_val
                elif s_type == CISCO_SENSOR_TYPE_DBM:
                    # Distinguish tx vs rx by sensor name heuristics
                    s_name_lower = s_name.lower()
                    if "transmit" in s_name_lower or "tx" in s_name_lower:
                        tx_powers.append(actual_val)
                    elif "receive" in s_name_lower or "rx" in s_name_lower:
                        rx_powers.append(actual_val)
                    else:
                        # Unknown direction; alternate tx/rx assignment
                        if len(tx_powers) <= len(rx_powers):
                            tx_powers.append(actual_val)
                        else:
                            rx_powers.append(actual_val)

            # Build channel list — pair tx/rx by position
            num_channels = max(len(tx_powers), len(rx_powers), 1)
            channels: list[TransceiverChannelData] = []
            for ch in range(num_channels):
                tx_pwr = tx_powers[ch] if ch < len(tx_powers) else None
                rx_pwr = rx_powers[ch] if ch < len(rx_powers) else None
                # Skip channels with no power data at all
                if tx_pwr is None and rx_pwr is None:
                    continue
                channels.append(
                    TransceiverChannelData(
                        channel=ch + 1,
                        tx_power=tx_pwr,
                        rx_power=rx_pwr,
                    ),
                )

            if not channels and temperature is None and voltage is None:
                continue  # No useful data for this entity

            # Ensure at least one channel exists for the data model
            if not channels:
                channels = [
                    TransceiverChannelData(
                        channel=1, tx_power=None, rx_power=None,
                    ),
                ]

            results.append(
                TransceiverData(
                    interface_name=iface_name,
                    temperature=temperature,
                    voltage=voltage,
                    channels=channels,
                ),
            )

        all_varbinds = (
            value_varbinds + type_varbinds + scale_varbinds
            + prec_varbinds + name_varbinds + contained_varbinds
        )
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
