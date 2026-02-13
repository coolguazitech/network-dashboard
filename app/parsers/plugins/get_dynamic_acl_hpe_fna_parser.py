"""
Parser for 'get_dynamic_acl_hpe_fna' API.

Parses HPE Comware ``display mac-authentication verbose`` output for
dynamically applied ACL bindings.  Also supports a CSV fallback format.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import AclData, BaseParser
from app.parsers.registry import parser_registry


class GetDynamicAclHpeFnaParser(BaseParser[AclData]):
    """
    Parser for HPE dynamic ACL bindings from MAC authentication output.

    Primary format (``display mac-authentication verbose``):
    ```
    Interface         MAC Address        ACL Number  Auth State
    GE1/0/1           aabb-ccdd-0001     3001        Authenticated
    GE1/0/2           aabb-ccdd-0002     --          Unauthenticated
    GE1/0/3           aabb-ccdd-0003     3001        Authenticated
    ```

    CSV fallback:
    ```
    Interface,ACL
    GE1/0/1,3001
    GE1/0/2,
    ```
    """

    device_type = DeviceType.HPE
    command = "get_dynamic_acl_hpe_fna"

    # Tabular data row: interface, MAC, ACL number (or --), auth state
    # Flexible whitespace-separated columns
    TABLE_ROW_PATTERN = re.compile(
        r"^(\S+)\s+"            # interface
        r"([0-9a-fA-F]{4}[.\-][0-9a-fA-F]{4}[.\-][0-9a-fA-F]{4}|"
        r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-]"
        r"[0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})\s+"  # MAC
        r"(\S+)\s+"             # ACL number or "--"
        r"(\S+)\s*$",           # auth state
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
parser_registry.register(GetDynamicAclHpeFnaParser())
