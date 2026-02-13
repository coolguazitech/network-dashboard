"""
Parser for 'get_static_acl_ios_fna' API.

Parses Cisco IOS ``show running-config`` output for interface ACL bindings
(ip access-group rules).  Also supports a CSV fallback format.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import AclData, BaseParser
from app.parsers.registry import parser_registry


class GetStaticAclIosFnaParser(BaseParser[AclData]):
    """
    Parser for Cisco IOS static ACL bindings from running configuration.

    Primary format (``show running-config``):
    ```
    interface GigabitEthernet1/0/1
     ip access-group 101 in
    interface GigabitEthernet1/0/2
     ip access-group 102 in
    interface GigabitEthernet1/0/3
    ```

    CSV fallback:
    ```
    Interface,ACL
    Gi1/0/1,101
    Gi1/0/2,
    ```
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_static_acl_ios_fna"

    # Matches "interface <name>" lines in IOS config
    INTERFACE_PATTERN = re.compile(
        r"^interface\s+(\S+)", re.MULTILINE | re.IGNORECASE
    )

    # Matches "ip access-group <acl> in/out" under an interface
    ACCESS_GROUP_PATTERN = re.compile(
        r"^\s+ip\s+access-group\s+(\S+)", re.MULTILINE | re.IGNORECASE
    )

    # CSV row: Interface,ACL  (ACL may be empty)
    CSV_ROW_PATTERN = re.compile(
        r"^([^,\s]+)\s*,\s*(.*?)\s*$", re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[AclData]:
        results: list[AclData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Try CLI block format first
        if self.INTERFACE_PATTERN.search(raw_output):
            results = self._parse_cli_format(raw_output)

        # Fall back to CSV if no CLI results found
        if not results and "," in raw_output:
            results = self._parse_csv_format(raw_output)

        return results

    def _parse_cli_format(self, raw_output: str) -> list[AclData]:
        """Parse IOS running-config style interface blocks."""
        results: list[AclData] = []

        interface_matches = list(self.INTERFACE_PATTERN.finditer(raw_output))

        for i, match in enumerate(interface_matches):
            interface_name = match.group(1)
            start = match.end()
            end = (
                interface_matches[i + 1].start()
                if i + 1 < len(interface_matches)
                else len(raw_output)
            )
            block = raw_output[start:end]

            # Look for ip access-group within this interface block
            ag_match = self.ACCESS_GROUP_PATTERN.search(block)
            acl_number = ag_match.group(1) if ag_match else None

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
parser_registry.register(GetStaticAclIosFnaParser())
