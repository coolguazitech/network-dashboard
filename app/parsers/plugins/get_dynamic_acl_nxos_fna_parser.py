"""
Parser for 'get_dynamic_acl_nxos_fna' API.

Parses Cisco NX-OS dynamic ACL bindings.  NX-OS does NOT have
``show authentication sessions``; it uses ``show dot1x all summary``
or ``show port-security interface`` for authentication status.
Also supports a CSV fallback format.

=== ParsedData Model (DO NOT REMOVE) ===
class AclData(ParsedData):
    interface_name: str                      # e.g. "GigabitEthernet1/0/1"
    acl_number: str | None = None            # ACL number/name, None if no ACL bound
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show dot1x all det
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import AclData, BaseParser
from app.parsers.registry import parser_registry


class GetDynamicAclNxosFnaParser(BaseParser[AclData]):
    """
    Parser for Cisco NX-OS dynamic ACL bindings.

    Real CLI ``show dot1x all summary`` (ref: Cisco NX-OS docs)::

           Interface     PAE              Client          Status
        ------------------------------------------------------------------
             Ethernet1/1    AUTH                none    UNAUTHORIZED

           Interface     PAE              Client          Status
        ------------------------------------------------------------------
            Ethernet1/33    AUTH   00:16:5A:4C:00:07      AUTHORIZED
                                   00:16:5A:4C:00:06      AUTHORIZED

    The FNA API may transform this to include ACL bindings::

        Interface         MAC Address        ACL         Status
        Eth1/1            aabb.ccdd.0001     101         Authorized
        Eth1/2            aabb.ccdd.0002     --          Unauthorized

    CSV fallback::

        Interface,ACL
        Eth1/1,101
        Eth1/2,

    Notes:
        - NX-OS uses ``show dot1x`` instead of IOS ``show authentication sessions``.
        - Exact FNA output format depends on API transformation layer.
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

    # Known auth-state values (lowercase) — used to distinguish ACL vs auth columns
    AUTH_STATE_KEYWORDS = {
        "authenticated", "unauthenticated", "authorized", "unauthorized",
        "mac-auth", "auth", "unauth",
    }

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

    def _pick_acl_value(self, col3: str, col4: str) -> str:
        """Determine which column holds the ACL number.

        Column order may vary between firmware versions:
          - Interface | MAC | ACL Number | Status  → col3 = ACL
          - Interface | MAC | Status | ACL Number  → col4 = ACL
        """
        c3 = col3.strip()
        c4 = col4.strip()
        if c3.lower() in self.AUTH_STATE_KEYWORDS:
            return c4
        if c4.lower() in self.AUTH_STATE_KEYWORDS:
            return c3
        if c3.isdigit() or c3 in ("--", "-", "N/A", ""):
            return c3
        return c4

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

            acl_val = self._pick_acl_value(match.group(3), match.group(4))
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
