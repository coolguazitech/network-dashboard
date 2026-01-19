"""
HPE Transceiver Parser Plugin.

Parses transceiver output from HPE ProCurve/Comware devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class HpeProCurveTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for HPE ProCurve transceiver data.

    Parses output from: show interfaces transceiver
    """

    vendor = VendorType.HPE
    platform = PlatformType.HPE_PROCURVE
    indicator_type = "transceiver"
    command = "show interfaces transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse HPE ProCurve transceiver output.

        Example output format:
        Port  Type        Rx (dBm)  Tx (dBm)  Temp (C)
        ----  ----------  --------  --------  --------
        1     SFP+LR      -3.2      -2.1      35.5
        2     SFP+SR      -2.8      -1.9      34.2

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        lines = raw_output.strip().split("\n")

        in_data_section = False

        for line in lines:
            if not line.strip():
                continue

            # Check for separator line
            if re.match(r"^[\s-]+$", line):
                in_data_section = True
                continue

            if not in_data_section:
                continue

            # Parse data line
            parts = line.split()
            if len(parts) >= 4:
                try:
                    interface = parts[0]
                    # Skip type column, get rx, tx, temp
                    rx_power = self._parse_float(parts[2])
                    tx_power = self._parse_float(parts[3])
                    temp = None
                    if len(parts) >= 5:
                        temp = self._parse_float(parts[4])

                    if tx_power is not None or rx_power is not None:
                        results.append(
                            TransceiverData(
                                interface_name=interface,
                                tx_power=tx_power,
                                rx_power=rx_power,
                                temperature=temp,
                            )
                        )
                except (ValueError, IndexError):
                    continue

        return results

    def _parse_float(self, value: str) -> float | None:
        """Parse float value, returning None for N/A or invalid."""
        if value.lower() in ("n/a", "-", "--", ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None


class HpeComwareTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for HPE Comware transceiver data.

    Parses output from: display transceiver
    """

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "transceiver"
    command = "display transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse HPE Comware transceiver output.

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        current_interface: str | None = None
        current_data: dict[str, float | None] = {}

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Match interface line
            interface_match = re.match(
                r"^(GigabitEthernet|Ten-GigabitEthernet)\d+/\d+/\d+",
                line,
            )
            if interface_match:
                if current_interface and self._has_data(current_data):
                    results.append(
                        self._create_data(current_interface, current_data)
                    )
                current_interface = interface_match.group(0)
                current_data = {}
                continue

            # Parse Tx Power
            tx_match = re.search(r"TX Power\s*:\s*([\d.-]+)\s*dBm", line)
            if tx_match:
                current_data["tx_power"] = float(tx_match.group(1))

            # Parse Rx Power
            rx_match = re.search(r"RX Power\s*:\s*([\d.-]+)\s*dBm", line)
            if rx_match:
                current_data["rx_power"] = float(rx_match.group(1))

            # Parse Temperature
            temp_match = re.search(r"Temperature\s*:\s*([\d.-]+)\s*C", line)
            if temp_match:
                current_data["temperature"] = float(temp_match.group(1))

        # Last interface
        if current_interface and self._has_data(current_data):
            results.append(self._create_data(current_interface, current_data))

        return results

    def _has_data(self, data: dict[str, float | None]) -> bool:
        """Check if data has at least tx or rx power."""
        return data.get("tx_power") is not None or \
            data.get("rx_power") is not None

    def _create_data(
        self,
        interface: str,
        data: dict[str, float | None],
    ) -> TransceiverData:
        """Create TransceiverData from parsed data."""
        return TransceiverData(
            interface_name=interface,
            tx_power=data.get("tx_power"),
            rx_power=data.get("rx_power"),
            temperature=data.get("temperature"),
        )


# Register parsers
parser_registry.register(HpeProCurveTransceiverParser())
parser_registry.register(HpeComwareTransceiverParser())
