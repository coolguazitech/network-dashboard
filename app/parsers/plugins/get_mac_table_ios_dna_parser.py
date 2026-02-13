"""Parser for 'get_mac_table_ios_dna' API."""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, MacTableData
from app.parsers.registry import parser_registry


class GetMacTableIosDnaParser(BaseParser[MacTableData]):
    """
    Parser for Cisco IOS ``show mac address-table`` output.

    Handles two formats:

    Format A — real IOS CLI (ref: NTC-templates ``cisco_ios_show_mac-address-table.raw``)::

                  Mac Address Table
        -------------------------------------------

        Vlan    Mac Address       Type        Ports
        ----    -----------       --------    -----
         100    0100.5e00.0001    STATIC      CPU
          10    68a8.2845.7640    DYNAMIC     Gi1/0/3
          20    7c0e.ceca.9548    DYNAMIC     Gi1/0/1
        Total Mac Addresses for this criterion: 3

    Format B — CSV::

        MAC,Interface,VLAN
        AA:BB:CC:DD:EE:01,GE1/0/1,10

    Notes:
        - MAC format: xxxx.xxxx.xxxx (Cisco dotted). Pydantic auto-normalizes.
        - VLAN range validated: 1-4094.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_mac_table_ios_dna"

    # IOS data row: VLAN  MAC(xxxx.xxxx.xxxx)  Type  Port
    ROW_PATTERN = re.compile(
        r"^\s*(?P<vlan>\d+)\s+"
        r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
        r"\S+\s+"  # Type (DYNAMIC, STATIC, etc.)
        r"(?P<port>\S+)",
        re.MULTILINE,
    )

    def parse(self, raw_output: str) -> list[MacTableData]:
        results: list[MacTableData] = []

        if not raw_output or not raw_output.strip():
            return results

        if self._is_csv(raw_output):
            return self._parse_csv(raw_output)

        return self._parse_cli(raw_output)

    def _is_csv(self, raw_output: str) -> bool:
        """Detect CSV format by checking if the first non-empty line contains commas."""
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped:
                return "," in stripped and "MAC" in stripped.upper()
        return False

    def _parse_csv(self, raw_output: str) -> list[MacTableData]:
        """Parse CSV format output."""
        results: list[MacTableData] = []
        reader = csv.DictReader(StringIO(raw_output.strip()))
        for row in reader:
            try:
                mac = (row.get("MAC") or "").strip()
                interface = (row.get("Interface") or "").strip()
                vlan_str = (row.get("VLAN") or "").strip()
                if not mac or not interface or not vlan_str:
                    continue
                vlan_id = int(vlan_str)
                if not (1 <= vlan_id <= 4094):
                    continue
                results.append(
                    MacTableData(
                        mac_address=mac,
                        interface_name=interface,
                        vlan_id=vlan_id,
                    )
                )
            except (ValueError, KeyError):
                continue
        return results

    def _parse_cli(self, raw_output: str) -> list[MacTableData]:
        """Parse Cisco IOS CLI table output."""
        results: list[MacTableData] = []
        for match in self.ROW_PATTERN.finditer(raw_output):
            try:
                vlan_id = int(match.group("vlan"))
                if not (1 <= vlan_id <= 4094):
                    continue
                results.append(
                    MacTableData(
                        mac_address=match.group("mac"),
                        interface_name=match.group("port"),
                        vlan_id=vlan_id,
                    )
                )
            except (ValueError, KeyError):
                continue
        return results


# Register parser
parser_registry.register(GetMacTableIosDnaParser())
