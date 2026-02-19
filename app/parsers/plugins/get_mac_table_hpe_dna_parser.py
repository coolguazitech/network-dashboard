"""Parser for 'get_mac_table_hpe_dna' API.

=== ParsedData Model (DO NOT REMOVE) ===
class MacTableData(ParsedData):
    mac_address: str                         # auto-normalized → AA:BB:CC:DD:EE:FF
    interface_name: str                      # port name
    vlan_id: int                             # VLAN ID (1-4094)
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display mac-address
=== End Real CLI Command ===
"""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, MacTableData
from app.parsers.registry import parser_registry


class GetMacTableHpeDnaParser(BaseParser[MacTableData]):
    """
    Parser for HPE Comware ``display mac-address`` output.

    Handles two formats:

    Format A — real HPE CLI (ref: NTC-templates ``hp_comware_display_mac-address.raw``)::

        MAC ADDR          VLAN ID  STATE          PORT INDEX       AGING TIME(s)
        000c-29aa-bb01    100      Learned        GigabitEthernet1/0/1   AGING
        000c-29aa-bb02    200      Learned        GigabitEthernet1/0/2   AGING
        000c-29aa-bb03    10       Security       GigabitEthernet1/0/3   NOAGED

    Format B — CSV::

        MAC,Interface,VLAN
        AA:BB:CC:DD:EE:01,GE1/0/1,10

    Notes:
        - MAC format: xxxx-xxxx-xxxx (HPE hyphenated). Pydantic auto-normalizes.
        - VLAN range validated: 1-4094.
    """

    device_type = DeviceType.HPE
    command = "get_mac_table_hpe_dna"

    # HPE Comware data row: MAC(xxxx-xxxx-xxxx)  VLAN  State  Port
    ROW_PATTERN = re.compile(
        r"^\s*(?P<mac>[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+"
        r"(?P<vlan>\d+)\s+"
        r"\S+\s+"  # State (Learned, Security, etc.)
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
        """Parse HPE Comware CLI table output."""
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
parser_registry.register(GetMacTableHpeDnaParser())
