"""
Parser for 'get_uplink_cdp_nxos_dna' API.

Parses Cisco NX-OS `show cdp neighbors detail` output to extract
CDP neighbor details (remote hostname, interface, platform).

=== ParsedData Model (DO NOT REMOVE) ===
class NeighborData(ParsedData):
    local_interface: str                     # local port, e.g. "GigabitEthernet0/1"
    remote_hostname: str                     # neighbor device name
    remote_interface: str                    # neighbor port
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show cdp neighbors detail
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class GetUplinkCdpNxosDnaParser(BaseParser[NeighborData]):
    """
    Parser for Cisco NX-OS ``show cdp neighbors detail`` output.

    Real CLI output::

        ----------------------------------------
        Device ID:SPINE-01(SSI12345678)
        System Name: SPINE-01

        Interface address(es):
            IPv4 Address: 10.0.0.1
        Platform: N9K-C93180YC-EX, Capabilities: Router Switch IGMP Filtering Supports-STP-Dispute
        Interface: Ethernet1/1, Port ID (outgoing port): Ethernet1/25
        Holdtime: 155 sec

        Version:
        Cisco Nexus Operating System (NX-OS) Software, Version 9.3(8)

        Advertisement Version: 2
        ----------------------------------------
        Device ID:SPINE-02(SSI12345679)
        System Name: SPINE-02

        Interface address(es):
            IPv4 Address: 10.0.0.2
        Platform: N9K-C93180YC-EX, Capabilities: Router Switch IGMP Filtering
        Interface: Ethernet1/2, Port ID (outgoing port): Ethernet1/25
        Holdtime: 148 sec

    Notes:
        - Blocks separated by lines of 10+ dashes.
        - Device ID may include serial number in parentheses.
        - Platform text before first comma is extracted.
        - NX-OS CDP output is very similar to IOS CDP output.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_uplink_cdp_nxos_dna"

    # CDP detail patterns
    DEVICE_ID_PATTERN = re.compile(r'Device ID:\s*(.+)')
    INTERFACE_PATTERN = re.compile(
        r'Interface:\s*(\S+?)\s*,\s*Port ID \(outgoing port\):\s*(\S+)'
    )

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse Cisco NX-OS CDP neighbor detail output into NeighborData records.

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
        raw_device_id = device_match.group(1).strip()
        if not raw_device_id:
            return None
        # Remove serial number suffix like "(SSI12345678)"
        remote_hostname = re.sub(r'\(.*?\)\s*$', '', raw_device_id).strip()
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

        return NeighborData(
            local_interface=local_interface,
            remote_hostname=remote_hostname,
            remote_interface=remote_interface,
        )


# Register parser
parser_registry.register(GetUplinkCdpNxosDnaParser())
