"""
Cisco IOS Transceiver Parser Plugin.

Parses 'show interfaces transceiver' output from Cisco IOS devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class CiscoIosTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for Cisco IOS transceiver data.

    Parses output from: show interfaces transceiver
    Tested with: Catalyst series
    """

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_IOS
    indicator_type = "transceiver"
    command = "show interfaces transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse IOS transceiver output.

        Example output format (table style):
                                     Optical   Optical
                   Temperature  Voltage  Tx Power  Rx Power
        Port       (Celsius)    (Volts)  (dBm)     (dBm)
        ---------  -----------  -------  --------  --------
        Gi1/0/1    32.5         3.29     -2.1      -3.5
        Gi1/0/2    31.8         3.30     -1.8      -2.9

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        lines = raw_output.strip().split("\n")

        # Find the data section (after the header line with dashes)
        in_data_section = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Check for separator line (----)
            if re.match(r"^[\s-]+$", line):
                in_data_section = True
                continue

            if not in_data_section:
                continue

            # Parse data line
            # Format: Port  Temp  Voltage  TxPower  RxPower
            parts = line.split()
            if len(parts) >= 5:
                try:
                    interface = parts[0]
                    temp = self._parse_float(parts[1])
                    voltage = self._parse_float(parts[2])
                    tx_power = self._parse_float(parts[3])
                    rx_power = self._parse_float(parts[4])

                    if tx_power is not None or rx_power is not None:
                        results.append(
                            TransceiverData(
                                interface_name=interface,
                                tx_power=tx_power,
                                rx_power=rx_power,
                                temperature=temp,
                                voltage=voltage,
                            )
                        )
                except (ValueError, IndexError):
                    # Skip malformed lines
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


# Register the parser
parser_registry.register(CiscoIosTransceiverParser())
