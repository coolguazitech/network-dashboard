"""Parser for 'get_arp_table_nxos_fna' API."""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import ArpData, BaseParser
from app.parsers.registry import parser_registry


class GetArpTableNxosFnaParser(BaseParser[ArpData]):
    """
    Parser for Cisco NX-OS ``show ip arp`` output.

    Handles two formats:

    Format A — real NX-OS CLI (ref: NTC-templates ``cisco_nxos_show_ip_arp.raw``)::

        Flags:  # - Adjacencies Throttled for Glean

        IP ARP Table for all contexts
        Total number of entries: 3
        Address         Age       MAC Address     Interface
        10.1.1.1        00:05:12  0012.3456.7890  Ethernet1/1
        10.1.1.2        00:10:30  0012.3456.7891  Ethernet1/2
        10.1.1.3             -    0012.3456.7892  mgmt0

    Format B — CSV::

        IP,MAC
        10.1.1.100,AA:BB:CC:DD:EE:01

    Notes:
        - Age format: HH:MM:SS or ``-`` for static entries.
        - MAC format: xxxx.xxxx.xxxx (Cisco dotted). Pydantic auto-normalizes.
        - Header/flags lines are skipped by regex (only data rows match).
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_arp_table_nxos_fna"

    # Match: IP  Age(HH:MM:SS or -)  MAC(Cisco dotted)
    ROW_PATTERN = re.compile(
        r"^\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?:\S+)\s+"  # Age (HH:MM:SS or -)
        r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})",
        re.MULTILINE,
    )

    def parse(self, raw_output: str) -> list[ArpData]:
        results: list[ArpData] = []

        if not raw_output or not raw_output.strip():
            return results

        if self._is_csv(raw_output):
            return self._parse_csv(raw_output)

        return self._parse_cli(raw_output)

    def _is_csv(self, raw_output: str) -> bool:
        """Detect CSV format by checking if the first non-empty line looks like a CSV header."""
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped:
                return "," in stripped and "IP" in stripped.upper()
        return False

    def _parse_csv(self, raw_output: str) -> list[ArpData]:
        """Parse CSV format output."""
        results: list[ArpData] = []
        reader = csv.DictReader(StringIO(raw_output.strip()))
        for row in reader:
            try:
                ip = (row.get("IP") or "").strip()
                mac = (row.get("MAC") or "").strip()
                if not ip or not mac:
                    continue
                if mac.lower() == "incomplete":
                    continue
                results.append(
                    ArpData(
                        ip_address=ip,
                        mac_address=mac,
                    )
                )
            except (ValueError, KeyError):
                continue
        return results

    def _parse_cli(self, raw_output: str) -> list[ArpData]:
        """Parse Cisco NX-OS CLI output."""
        results: list[ArpData] = []
        for match in self.ROW_PATTERN.finditer(raw_output):
            results.append(
                ArpData(
                    ip_address=match.group("ip"),
                    mac_address=match.group("mac"),
                )
            )
        return results


# Register parser
parser_registry.register(GetArpTableNxosFnaParser())
