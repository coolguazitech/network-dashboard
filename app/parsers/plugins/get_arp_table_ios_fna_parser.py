"""Parser for 'get_arp_table_ios_fna' API."""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import ArpData, BaseParser
from app.parsers.registry import parser_registry


class GetArpTableIosFnaParser(BaseParser[ArpData]):
    """
    Parser for Cisco IOS/IOS-XE ``show ip arp`` output.

    Handles two formats:

    Format A — real IOS CLI (ref: NTC-templates ``cisco_ios_show_ip_arp.raw``)::

        Protocol  Address          Age (min)  Hardware Addr   Type   Interface
        Internet  172.16.233.229          -   0000.0c07.ac01  ARPA   Vlan210
        Internet  172.16.233.218          0   7c0e.ceca.9548  ARPA   Vlan210
        Internet  172.16.233.236         72   7c0e.ceca.9500  ARPA   Vlan210
        Internet  172.16.233.208          -   Incomplete      ARPA

    Format B — CSV::

        IP,MAC
        10.1.1.100,AA:BB:CC:DD:EE:01

    Notes:
        - MAC format: xxxx.xxxx.xxxx (Cisco dotted). Pydantic auto-normalizes.
        - ``Incomplete`` entries are skipped (regex only matches hex dotted MACs).
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_arp_table_ios_fna"

    # Match: Internet  IP  Age  MAC(Cisco dotted)  Type  [Interface]
    ROW_PATTERN = re.compile(
        r"^\s*Internet\s+"
        r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?:\S+)\s+"  # Age (numeric or -)
        r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
        r"(?:ARPA|SNAP|SAP)",
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
        """Parse Cisco IOS CLI output."""
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
parser_registry.register(GetArpTableIosFnaParser())
