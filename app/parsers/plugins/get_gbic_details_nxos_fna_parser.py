"""
Parser for 'get_gbic_details_nxos_fna' API.

Parses Cisco NX-OS `show interface transceiver details` per-interface block output.

Real CLI command: show interface transceiver details
Platforms: Nexus 3000, 5000, 7000, 9000 series
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.protocols import TransceiverChannelData
from app.parsers.registry import parser_registry


class GetGbicDetailsNxosFnaParser(BaseParser[TransceiverData]):
    """
    Parser for Cisco NX-OS `show interface transceiver details` output.

    SFP format (per-interface block with threshold table):
    ```
    Ethernet1/1
        transceiver is present
        type is 10Gbase-SR
        ...
        SFP Detail Diagnostics Information (internal calibration)
        ------------------------------------------------------------
                           High Alarm  High Warn  Low Warn   Low Alarm
           Measurement     Threshold   Threshold  Threshold  Threshold
        Temperature  34.41 C      75.00 C     70.00 C    0.00 C     -5.00 C
        Voltage      3.22 V       3.63 V      3.46 V     2.97 V     3.13 V
        Current      9.89 mA      70.00 mA    68.00 mA   1.00 mA    2.00 mA
        Tx Power    -1.29 dBm     3.49 dBm    0.49 dBm  -12.19 dBm -8.19 dBm
        Rx Power    -9.26 dBm     3.49 dBm    0.49 dBm  -18.38 dBm -14.40 dBm
        Transmit Fault Count = 0
    ```

    QSFP format (module-level temp/voltage + per-lane table):
    ```
    Ethernet1/49
        transceiver is present
        type is QSFP-40G-SR4
        ...
        QSFP Detail Diagnostics Information (internal calibration)
        ============================================================
        Temperature : 32.15 C
        Voltage     : 3.30 V

              Tx Bias     Tx Power    Rx Power
        Lane  Current     (dBm)       (dBm)
        ----  -------     --------    --------
        1     6.51        -1.50       -2.10
        2     6.48        -1.55       -2.30
        3     6.52        -1.48       -2.05
        4     6.45        -1.52       -2.20
    ```

    Notes:
    - "transceiver is not present" → skip
    - SFP: Temperature/Voltage/Current/Tx/Rx in threshold table, single channel
    - QSFP: Module-level temp/voltage, per-lane bias/tx/rx
    - Interface names: Ethernet1/1, Ethernet1/49, mgmt0
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_gbic_details_nxos_fna"

    # Match interface block headers: "Ethernet1/1" or "mgmt0" at start of line
    INTERFACE_PATTERN = re.compile(
        r'^(?P<interface>(?:Ethernet|mgmt)\S*)\s*$',
        re.MULTILINE
    )

    # SFP diagnostics: "Temperature  34.41 C" (first value is measurement)
    SFP_TEMP_PATTERN = re.compile(
        r'Temperature\s+(?P<val>-?\d+(?:\.\d+)?)\s*C', re.IGNORECASE
    )
    SFP_VOLTAGE_PATTERN = re.compile(
        r'Voltage\s+(?P<val>\d+(?:\.\d+)?)\s*V', re.IGNORECASE
    )
    SFP_CURRENT_PATTERN = re.compile(
        r'Current\s+(?P<val>\d+(?:\.\d+)?)\s*mA', re.IGNORECASE
    )
    SFP_TX_PATTERN = re.compile(
        r'Tx\s*Power\s+(?P<val>-?\d+(?:\.\d+)?)\s*dBm', re.IGNORECASE
    )
    SFP_RX_PATTERN = re.compile(
        r'Rx\s*Power\s+(?P<val>-?\d+(?:\.\d+)?)\s*dBm', re.IGNORECASE
    )

    # QSFP module-level: "Temperature : 32.15 C" or "Voltage : 3.30 V"
    QSFP_TEMP_PATTERN = re.compile(
        r'Temperature\s*:\s*(?P<val>-?\d+(?:\.\d+)?)\s*C', re.IGNORECASE
    )
    QSFP_VOLTAGE_PATTERN = re.compile(
        r'Voltage\s*:\s*(?P<val>\d+(?:\.\d+)?)\s*V', re.IGNORECASE
    )

    # QSFP per-lane data rows: "1  6.51  -1.50  -2.10"
    QSFP_LANE_PATTERN = re.compile(
        r'^\s*(?P<lane>[1-4])\s+(?P<bias>\d+(?:\.\d+)?)\s+(?P<tx>-?\d+(?:\.\d+)?)\s+(?P<rx>-?\d+(?:\.\d+)?)',
        re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[TransceiverData]:
        results: list[TransceiverData] = []

        # Split into per-interface blocks
        blocks = self._split_by_interface(raw_output)

        for interface_name, block in blocks:
            # Skip absent transceivers
            if 'not present' in block.lower():
                continue

            data = self._parse_block(interface_name, block)
            if data:
                results.append(data)

        return results

    def _split_by_interface(self, output: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        matches = list(self.INTERFACE_PATTERN.finditer(output))

        for i, match in enumerate(matches):
            interface = match.group('interface')
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
            blocks.append((interface, output[start:end]))

        return blocks

    def _parse_block(self, interface_name: str, block: str) -> TransceiverData | None:
        is_qsfp = 'QSFP' in block.upper() or 'qsfp' in block.lower()

        if is_qsfp:
            return self._parse_qsfp_block(interface_name, block)
        else:
            return self._parse_sfp_block(interface_name, block)

    def _parse_sfp_block(self, interface_name: str, block: str) -> TransceiverData | None:
        """Parse SFP-style block with threshold table."""
        temp_m = self.SFP_TEMP_PATTERN.search(block)
        voltage_m = self.SFP_VOLTAGE_PATTERN.search(block)
        current_m = self.SFP_CURRENT_PATTERN.search(block)
        tx_m = self.SFP_TX_PATTERN.search(block)
        rx_m = self.SFP_RX_PATTERN.search(block)

        # Need at least temperature or power data
        if not temp_m and not tx_m and not rx_m:
            return None

        temperature = float(temp_m.group('val')) if temp_m else None
        voltage = float(voltage_m.group('val')) if voltage_m else None

        channel = TransceiverChannelData(
            channel=1,
            tx_power=float(tx_m.group('val')) if tx_m else None,
            rx_power=float(rx_m.group('val')) if rx_m else None,
            bias_current_ma=float(current_m.group('val')) if current_m else None,
        )

        return TransceiverData(
            interface_name=interface_name,
            temperature=temperature,
            voltage=voltage,
            channels=[channel],
        )

    def _parse_qsfp_block(self, interface_name: str, block: str) -> TransceiverData | None:
        """Parse QSFP-style block with module temp/voltage + per-lane table."""
        temp_m = self.QSFP_TEMP_PATTERN.search(block)
        voltage_m = self.QSFP_VOLTAGE_PATTERN.search(block)

        temperature = float(temp_m.group('val')) if temp_m else None
        voltage = float(voltage_m.group('val')) if voltage_m else None

        # Parse per-lane data
        channels: list[TransceiverChannelData] = []
        for lane_m in self.QSFP_LANE_PATTERN.finditer(block):
            channels.append(TransceiverChannelData(
                channel=int(lane_m.group('lane')),
                bias_current_ma=float(lane_m.group('bias')),
                tx_power=float(lane_m.group('tx')),
                rx_power=float(lane_m.group('rx')),
            ))

        if not channels:
            # Fallback: try SFP-style parsing (some QSFP modules report single-channel)
            return self._parse_sfp_block(interface_name, block)

        return TransceiverData(
            interface_name=interface_name,
            temperature=temperature,
            voltage=voltage,
            channels=channels,
        )


# Register parser
parser_registry.register(GetGbicDetailsNxosFnaParser())
