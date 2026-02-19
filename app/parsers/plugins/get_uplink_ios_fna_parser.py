"""
Parser for 'get_uplink_ios_fna' API.

Parses Cisco IOS/IOS-XE `show cdp neighbors detail` output to extract
CDP neighbor details (remote hostname, interface, platform).

=== ParsedData Model (DO NOT REMOVE) ===
class NeighborData(ParsedData):
    local_interface: str                     # local port, e.g. "GigabitEthernet0/1"
    remote_hostname: str                     # neighbor device name
    remote_interface: str                    # neighbor port
    remote_platform: str | None = None       # optional platform description
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show cdp neighbor / show lldp neighbor
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class GetUplinkIosFnaParser(BaseParser[NeighborData]):
    """
    Parser for Cisco IOS/IOS-XE ``show cdp neighbors detail`` output.

    Real CLI output (ref: NTC-templates ``cisco_ios_show_cdp_neighbors_detail.raw``)::

        -------------------------
        Device ID: SW-CORE-01.example.com
        Entry address(es):
          IP address: 10.0.0.1
        Platform: cisco WS-C3750X-48PF,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
        Holdtime : 143 sec
        Version :
        Cisco IOS Software, C3750E Software, Version 15.2(4)E10
        -------------------------
        Device ID: SW-CORE-02
        Platform: cisco WS-C3750X-48PF,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
        Holdtime : 143 sec
        -------------------------

    Notes:
        - Blocks separated by lines of 10+ dashes.
        - Device ID may include domain suffix.
        - Platform text before comma is extracted.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_uplink_ios_fna"

    # CDP detail patterns
    DEVICE_ID_PATTERN = re.compile(r'Device ID:\s*(.+)')
    PLATFORM_PATTERN = re.compile(r'Platform:\s*(.+?)(?:,\s*Capabilities:|$)')
    INTERFACE_PATTERN = re.compile(
        r'Interface:\s*(\S+?)\s*,\s*Port ID \(outgoing port\):\s*(\S+)'
    )

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse Cisco IOS CDP neighbor detail output into NeighborData records.

        Args:
            raw_output: Raw CLI output from `show cdp neighbors detail`

        Returns:
            List of NeighborData, one per discovered CDP neighbor.
        """
        results: list[NeighborData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Split by separator lines (10 or more dashes)
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
        Parse a single CDP neighbor block.

        Returns None if required fields (Device ID, Interface, Port ID)
        are missing.
        """
        # Extract remote hostname (Device ID) - required
        device_match = self.DEVICE_ID_PATTERN.search(block)
        if not device_match:
            return None
        remote_hostname = device_match.group(1).strip()
        if not remote_hostname:
            return None

        # Extract local_interface and remote_interface - required
        intf_match = self.INTERFACE_PATTERN.search(block)
        if not intf_match:
            return None
        local_interface = intf_match.group(1).strip().rstrip(",")
        remote_interface = intf_match.group(2).strip()

        if not local_interface or not remote_interface:
            return None

        # Extract remote platform (Platform) - optional, text before comma
        remote_platform: str | None = None
        platform_match = self.PLATFORM_PATTERN.search(block)
        if platform_match:
            platform_val = platform_match.group(1).strip().rstrip(",")
            if platform_val:
                remote_platform = platform_val

        return NeighborData(
            local_interface=local_interface,
            remote_hostname=remote_hostname,
            remote_interface=remote_interface,
            remote_platform=remote_platform,
        )


# Register parser
parser_registry.register(GetUplinkIosFnaParser())
