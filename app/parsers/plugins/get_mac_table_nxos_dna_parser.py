"""Parser for 'get_mac_table_nxos_dna' API."""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, MacTableData
from app.parsers.registry import parser_registry


class GetMacTableNxosDnaParser(BaseParser[MacTableData]):
    """
    Parser for Cisco NX-OS ``show mac address-table`` output.

    Handles two formats:

    Format A — real NX-OS CLI (ref: NTC-templates ``cisco_nxos_show_mac_address-table.raw``)::

        Legend:
                * - primary entry, G - Gateway MAC, (R) - Routed MAC, O - Overlay MAC
                age - seconds since last seen,+ - primary entry using vPC Peer-Link

           VLAN     MAC Address      Type      age     Secure   NTFY   Ports
        ---------+-----------------+--------+---------+------+----+------------------
        *   10     5254.0012.d6e1   dynamic  0         F      F    Eth1/2
        *   10     5254.0018.39c9   dynamic  0         F      F    Eth1/1
        *   20     0050.5687.1abb   dynamic  0         F      F    Eth1/3
        G    -     5254.0001.0607   static   -         F      F    sup-eth1(R)

    Format B — CSV::

        MAC,Interface,VLAN
        AA:BB:CC:DD:EE:01,Eth1/1,10

    Notes:
        - Rows with VLAN ``-`` (Gateway/Routed MACs) are skipped (no valid VLAN).
        - VLAN range validated: 1-4094.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_mac_table_nxos_dna"

    # NXOS data row: optional flag(*/G/+)  VLAN(number or -)  MAC  Type  age  Secure  NTFY  Ports
    ROW_PATTERN = re.compile(
        r"^\s*[*G+]?\s*"
        r"(?P<vlan>\d+)\s+"
        r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
        r"\S+\s+"   # Type
        r"\S+\s+"   # age
        r"\S+\s+"   # Secure
        r"\S+\s+"   # NTFY
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
        """Parse Cisco NX-OS CLI table output."""
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
parser_registry.register(GetMacTableNxosDnaParser())
