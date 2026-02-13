"""Parser for 'get_arp_table_hpe_fna' API."""
from __future__ import annotations

import csv
import re
from io import StringIO

from app.core.enums import DeviceType
from app.parsers.protocols import ArpData, BaseParser
from app.parsers.registry import parser_registry


class GetArpTableHpeFnaParser(BaseParser[ArpData]):
    """
    Parser for HPE Comware ``display arp`` output.

    Handles two formats:

    Format A — real HPE CLI (ref: NTC-templates ``hp_comware_display_arp.raw``)::

        IP address      MAC address    SVLAN/VSI                  Interface         Aging Type
        10.1.1.1        000c-29aa-bb01 100                        GE1/0/1           20    Dynamic
        10.1.1.2        000c-29aa-bb02 200                        GE1/0/2           20    Dynamic
        10.1.1.3        Incomplete     --                         --                --    --

    Format B — CSV::

        IP,MAC
        10.1.1.100,AA:BB:CC:DD:EE:01

    Notes:
        - MAC format: xxxx-xxxx-xxxx (HPE hyphenated). Pydantic auto-normalizes.
        - ``Incomplete`` entries are skipped (regex only matches hex MACs).
    """

    device_type = DeviceType.HPE
    command = "get_arp_table_hpe_fna"

    # Match: IP  MAC(xxxx-xxxx-xxxx)  - skip Incomplete entries via MAC pattern
    ROW_PATTERN = re.compile(
        r"^\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?P<mac>[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})",
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
                # Skip incomplete-like entries in CSV (defensive)
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
        """Parse HPE Comware CLI output."""
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
parser_registry.register(GetArpTableHpeFnaParser())
