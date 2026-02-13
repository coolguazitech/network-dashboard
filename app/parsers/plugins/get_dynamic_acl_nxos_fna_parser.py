"""
Parser for 'get_dynamic_acl_nxos_fna' API.

Parses Cisco NX-OS dynamic ACL bindings.  NX-OS does NOT have
``show authentication sessions``; it uses ``show dot1x all summary``
or ``show port-security interface`` for authentication status.
Also supports a CSV fallback format.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import AclData, BaseParser
from app.parsers.registry import parser_registry


class GetDynamicAclNxosFnaParser(BaseParser[AclData]):
    """
    Parser for Cisco NX-OS dynamic ACL bindings.

    NX-OS does NOT have ``show authentication sessions`` (that's IOS only).
    The FNA API may use ``show dot1x all summary`` or similar::

        Interface  PAE    Client          Status        ACL
        Eth1/1     Auth   aabb.ccdd.0001  Authorized    101
        Eth1/2     Auth   aabb.ccdd.0002  Unauthorized  --

    Also handles generic tabular format::

        Interface         MAC Address        ACL         Status
        Eth1/1            aabb.ccdd.0001     101         Authorized
        Eth1/2            aabb.ccdd.0002     --          Unauthorized

    CSV fallback::

        Interface,ACL
        Eth1/1,101
        Eth1/2,

    Note: Exact FNA output format needs verification with real API.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_dynamic_acl_nxos_fna"

    # Tabular data row: interface, MAC (various formats), ACL number or "--", status
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
parser_registry.register(GetDynamicAclNxosFnaParser())
