"""
Cisco NX-OS Transceiver Parser Plugin.

Parses 'show interface transceiver' output from Cisco NX-OS devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class CiscoNxosTransceiverParser(BaseParser[TransceiverData]):
    """
    Parser for Cisco NX-OS transceiver data.

    Parses output from: show interface transceiver
    Tested with: Nexus 9000 series
    """

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "transceiver"
    command = "show interface transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse NX-OS transceiver output.

        Example output format:
        Ethernet1/1
            transceiver is present
            type is QSFP-40G-SR4
            name is CISCO-FINISAR
            part number is FTLX8571D3BCL-C2
            serial number is FNS12345678
            Temperature            30.32 C
            Voltage                3.28 V
            Current                6.45 mA
            Tx Power               -1.23 dBm
            Rx Power               -2.45 dBm

        Ethernet1/5
            transceiver is not present

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        current_interface: str | None = None
        current_data: dict[str, float | str | None] = {}
        is_present: bool = True  # 新增：追蹤光模塊是否存在

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Match interface line (e.g., "Ethernet1/1")
            interface_match = re.match(
                r"^(Ethernet\d+/\d+(?:/\d+)?)",
                line,
            )
            if interface_match:
                # Save previous interface data if exists
                if current_interface:
                    results.append(
                        self._create_transceiver_data(
                            current_interface,
                            current_data,
                            is_present,  # 傳遞光模塊存在狀態
                        )
                    )
                current_interface = interface_match.group(1)
                current_data = {}
                is_present = True  # 重置狀態
                continue

            # 檢測光模塊不存在
            if re.search(r"transceiver\s+is\s+not\s+present", line, re.IGNORECASE):
                is_present = False
                continue

            # Parse temperature
            temp_match = re.search(
                r"Temperature\s+([\d.-]+)\s*C",
                line,
                re.IGNORECASE,
            )
            if temp_match:
                current_data["temperature"] = float(temp_match.group(1))

            # Parse voltage
            voltage_match = re.search(
                r"Voltage\s+([\d.]+)\s*V",
                line,
                re.IGNORECASE,
            )
            if voltage_match:
                current_data["voltage"] = float(voltage_match.group(1))

            # Parse Tx Power
            tx_match = re.search(
                r"Tx\s+Power\s+([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if tx_match:
                current_data["tx_power"] = float(tx_match.group(1))

            # Parse Rx Power
            rx_match = re.search(
                r"Rx\s+Power\s+([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if rx_match:
                current_data["rx_power"] = float(rx_match.group(1))

            # Parse serial number
            serial_match = re.search(
                r"serial\s+number\s+is\s+(\S+)",
                line,
                re.IGNORECASE,
            )
            if serial_match:
                current_data["serial_number"] = serial_match.group(1)

            # Parse part number
            part_match = re.search(
                r"part\s+number\s+is\s+(\S+)",
                line,
                re.IGNORECASE,
            )
            if part_match:
                current_data["part_number"] = part_match.group(1)

        # Don't forget the last interface
        if current_interface:
            results.append(
                self._create_transceiver_data(
                    current_interface,
                    current_data,
                    is_present,
                )
            )

        return results

    def _create_transceiver_data(
        self,
        interface: str,
        data: dict[str, float | str | None],
        is_present: bool = True,
    ) -> TransceiverData:
        """
        Create TransceiverData from parsed data.
        
        如果光模塊不存在，所有值設為 None。
        """
        if not is_present:
            # 光模塊不存在，返回空數據但保留接口名稱
            return TransceiverData(
                interface_name=interface,
                tx_power=None,
                rx_power=None,
                temperature=None,
                voltage=None,
                serial_number=None,
                part_number=None,
            )
        
        return TransceiverData(
            interface_name=interface,
            tx_power=data.get("tx_power"),  # type: ignore
            rx_power=data.get("rx_power"),  # type: ignore
            temperature=data.get("temperature"),  # type: ignore
            voltage=data.get("voltage"),  # type: ignore
            serial_number=data.get("serial_number"),  # type: ignore
            part_number=data.get("part_number"),  # type: ignore
        )


# Register the parser
parser_registry.register(CiscoNxosTransceiverParser())
