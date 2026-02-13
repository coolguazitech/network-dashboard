"""
Parser for 'get_dynamic_acl_ios_fna' API.

Parses Cisco IOS ``show authentication sessions`` style output for
dynamically applied ACL bindings.  Also supports a CSV fallback format.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import AclData, BaseParser
from app.parsers.registry import parser_registry


class GetDynamicAclIosFnaParser(BaseParser[AclData]):
    """
    Parser for Cisco IOS dynamic ACL bindings from authentication sessions.

    Real CLI output (ref: NTC-templates ``cisco_ios_show_authentication_sessions.raw``)::

        Interface                MAC Address    Method  Domain  Status Fg  Session ID
        Gi1/0/1                  0050.5687.1234 mab     DATA    Auth      0A010101000000010050568712340000
        Gi1/0/2                  0050.5687.5678 dot1x   DATA    Unauth    0A010101000000020050568756780000

    FNA may transform this to include ACL bindings::

        Interface         MAC Address        ACL         Status
        Gi1/0/1           0050.5687.1234     101         Authorized
        Gi1/0/2           0050.5687.5678     --          Unauthorized

    CSV fallback::

        Interface,ACL
        Gi1/0/1,101
        Gi1/0/2,

    Note: Exact FNA output format needs verification with real API.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_dynamic_acl_ios_fna"

    # Tabular data row: interface, MAC (Cisco xxxx.xxxx.xxxx or colon-separated),
    # ACL number or "--", status
    TABLE_ROW_PATTERN = re.compile(
        r"^(\S+)\s+"            # interface
        r"([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}|"
        r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-]"
        r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}|"
        r"[0-9a-fA-F]{4}[.\-][0-9a-fA-F]{4}[.\-][0-9a-fA-F]{4})\s+"  # MAC
        r"(\S+)\s+"             # ACL number or "--"
        r"(\S+)\s*$",           # status
        re.MULTILINE,
    )

    # CSV row: Interface,ACL  (ACL may be empty)
    CSV_ROW_PATTERN = re.compile(
        r"^([^,\s]+)\s*,\s*(.*?)\s*$", re.MULTILINE
    )

    # Common header keywords to skip
    HEADER_KEYWORDS = {"interface", "port", "---"}

    def parse(self, raw_output: str) -> list[AclData]:
        results: list[AclData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Try tabular format first
        results = self._parse_table_format(raw_output)

        # Fall back to CSV if no tabular results found
        if not results and "," in raw_output:
            results = self._parse_csv_format(raw_output)

        return results

    def _parse_table_format(self, raw_output: str) -> list[AclData]:
        """Parse whitespace-delimited table output."""
        results: list[AclData] = []

        for match in self.TABLE_ROW_PATTERN.finditer(raw_output):
            interface_name = match.group(1)

            # Skip header rows
            if interface_name.lower() in self.HEADER_KEYWORDS:
                continue
            if interface_name.startswith("-"):
                continue

            acl_val = match.group(3).strip()
            acl_number = (
                None if acl_val in ("--", "-", "N/A", "") else acl_val
            )

            results.append(
                AclData(interface_name=interface_name, acl_number=acl_number)
            )

        return results

    def _parse_csv_format(self, raw_output: str) -> list[AclData]:
        """Parse CSV fallback format: Interface,ACL."""
        results: list[AclData] = []

        for match in self.CSV_ROW_PATTERN.finditer(raw_output):
            iface = match.group(1).strip()
            acl_val = match.group(2).strip()

            # Skip header row
            if iface.lower() == "interface":
                continue

            acl_number = acl_val if acl_val and acl_val != "--" else None
            results.append(
                AclData(interface_name=iface, acl_number=acl_number)
            )

        return results


# Register parser
parser_registry.register(GetDynamicAclIosFnaParser())
