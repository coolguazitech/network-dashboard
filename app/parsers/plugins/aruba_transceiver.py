"""
Aruba Transceiver Parser Plugin.

Parses transceiver output from Aruba AOS/AOS-CX devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class ArubaOsTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for Aruba AOS transceiver data.

    Parses output from: show interface transceiver
    """

    vendor = VendorType.ARUBA
    platform = PlatformType.ARUBA_OS
    indicator_type = "transceiver"
    command = "show interface transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse Aruba AOS transceiver output.

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
                    tx_power = self._parse_float(parts[-2])
                    rx_power = self._parse_float(parts[-1])

                    if tx_power is not None or rx_power is not None:
                        results.append(
                            TransceiverData(
                                interface_name=interface,
                                tx_power=tx_power,
                                rx_power=rx_power,
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


class ArubaCxTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for Aruba AOS-CX transceiver data.

    Parses output from: show interface transceiver
    """

    vendor = VendorType.ARUBA
    platform = PlatformType.ARUBA_CX
    indicator_type = "transceiver"
    command = "show interface transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse Aruba AOS-CX transceiver output.

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

            # Match interface line (e.g., "Interface 1/1/1")
            interface_match = re.match(
                r"^Interface\s+(\d+/\d+/\d+)",
                line,
                re.IGNORECASE,
            )
            if interface_match:
                if current_interface and self._has_data(current_data):
                    results.append(
                        self._create_data(current_interface, current_data)
                    )
                current_interface = interface_match.group(1)
                current_data = {}
                continue

            # Parse Tx Power
            tx_match = re.search(
                r"TX\s*Power.*?:\s*([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if tx_match:
                current_data["tx_power"] = float(tx_match.group(1))

            # Parse Rx Power
            rx_match = re.search(
                r"RX\s*Power.*?:\s*([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if rx_match:
                current_data["rx_power"] = float(rx_match.group(1))

            # Parse Temperature
            temp_match = re.search(
                r"Temperature.*?:\s*([\d.-]+)",
                line,
                re.IGNORECASE,
            )
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
parser_registry.register(ArubaOsTransceiverParser())
parser_registry.register(ArubaCxTransceiverParser())
