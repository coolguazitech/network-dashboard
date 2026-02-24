"""
Parser for 'get_uplink_lldp_ios_dna' API.

Parses Cisco IOS/IOS-XE `show lldp neighbors detail` output to extract
LLDP neighbor details (remote hostname, interface, platform).

=== ParsedData Model (DO NOT REMOVE) ===
class NeighborData(ParsedData):
    local_interface: str                     # local port, e.g. "GigabitEthernet0/1"
    remote_hostname: str                     # neighbor device name
    remote_interface: str                    # neighbor port
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show lldp neighbors detail
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class GetUplinkLldpIosDnaParser(BaseParser[NeighborData]):
    """
    Parser for Cisco IOS/IOS-XE ``show lldp neighbors detail`` output.

    Real CLI output::

        ------------------------------------------------
        Local Intf: Gi1/0/49
        Chassis id: 0026.980a.3c01
        Port id: Eth1/25
        Port Description: uplink
        System Name: SPINE-01

        System Description:
        Cisco IOS Software, Version 15.2(4)E10

        Time remaining: 102 seconds
        System Capabilities: B,R
        Enabled Capabilities: B,R
        Management Addresses:
            IP: 10.0.0.1

        ------------------------------------------------
        Local Intf: Gi1/0/50
        Chassis id: 0026.980a.3c02
        Port id: Eth1/25
        Port Description: uplink
        System Name: SPINE-02

        System Description:
        Cisco IOS Software, Version 15.2(4)E10

        Time remaining: 98 seconds

    Notes:
        - Blocks separated by dashed lines (10+ dashes) or
          split by ``Local Intf:`` lookahead.
        - Required fields: Local Intf, Port id, System Name.
        - ``not advertised`` values are treated as missing.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_uplink_lldp_ios_dna"

    # LLDP field patterns (IOS format)
    LOCAL_INTF_PATTERN = re.compile(
        r'^\s*Local Intf:\s*(?P<value>\S+)', re.MULTILINE
    )
    PORT_ID_PATTERN = re.compile(
        r'^\s*Port id:\s*(?P<value>\S+)', re.MULTILINE
    )
    SYSTEM_NAME_PATTERN = re.compile(
        r'^\s*System Name:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )
    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse IOS LLDP neighbor output into NeighborData records.

        Args:
            raw_output: Raw CLI output from `show lldp neighbors detail`

        Returns:
            List of NeighborData, one per discovered LLDP neighbor.
        """
        results: list[NeighborData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Split into blocks by dashed separator lines
        blocks = re.split(r'^-{10,}\s*$', raw_output, flags=re.MULTILINE)

        for block in blocks:
            if not block.strip():
                continue

            neighbor = self._parse_block(block)
            if neighbor is not None:
                results.append(neighbor)

        return results

    def _parse_block(self, block: str) -> NeighborData | None:
        """
        Parse a single LLDP neighbor block.

        Returns None if required fields (Local Intf, Port id,
        System Name) are missing.
        """
        # Extract local interface (Local Intf) - required
        local_match = self.LOCAL_INTF_PATTERN.search(block)
        if not local_match:
            return None
        local_interface = local_match.group("value").strip()
        if not local_interface:
            return None

        # Extract remote interface (Port id) - required
        port_id_match = self.PORT_ID_PATTERN.search(block)
        if not port_id_match:
            return None
        remote_interface = port_id_match.group("value").strip()
        if not remote_interface:
            return None

        # Extract remote hostname (System Name) - required
        name_match = self.SYSTEM_NAME_PATTERN.search(block)
        if not name_match:
            return None
        remote_hostname = name_match.group("value").strip()
        if not remote_hostname or "not advertised" in remote_hostname.lower():
            return None

        return NeighborData(
            local_interface=local_interface,
            remote_hostname=remote_hostname,
            remote_interface=remote_interface,
        )


# Register parser
parser_registry.register(GetUplinkLldpIosDnaParser())
