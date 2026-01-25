"""
Cisco IOS Neighbor Parser Plugin.

Parses 'show cdp neighbors detail' output from Cisco IOS devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class CiscoIosNeighborParser(BaseParser[NeighborData]):
    """
    Parser for Cisco IOS CDP neighbor data.

    Parses output from: show cdp neighbors detail
    Tested with: Catalyst 3750, 2960 series
    """

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_IOS
    indicator_type = "uplink"
    command = "show cdp neighbors detail"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse Cisco IOS CDP neighbor output.

        Example output format:
        -------------------------
        Device ID: Router01
        Entry address(es):
          IP address: 10.1.1.1
        Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24
        Holdtime : 179 sec

        Version :
        Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE11

        advertisement version: 2
        Protocol Hello:  OUI=0x00000C, Protocol ID=0x0112; payload len=27, value=00000000FFFFFFFF010221FF0000000000000000000000
        VTP Management Domain: 'DOMAIN01'
        Native VLAN: 1
        Duplex: full
        Management address(es):
          IP address: 10.1.1.1

        -------------------------
        Device ID: Switch02
        ...

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[NeighborData]: Parsed neighbor data
        """
        results: list[NeighborData] = []
        current_data: dict[str, str] = {}

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Separator line indicates start of new neighbor or end of previous
            if line.startswith("----"):
                # Save previous neighbor if complete
                if current_data and all(
                    k in current_data
                    for k in ["local_interface", "remote_hostname", "remote_interface"]
                ):
                    results.append(
                        NeighborData(
                            local_interface=current_data["local_interface"],
                            remote_hostname=current_data["remote_hostname"],
                            remote_interface=current_data["remote_interface"],
                            remote_platform=current_data.get("remote_platform"),
                        )
                    )
                    current_data = {}
                continue

            # Skip empty lines
            if not line:
                continue

            # Parse Device ID (remote hostname)
            # e.g., "Device ID: Router01"
            device_id_match = re.search(
                r"Device\s+ID:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if device_id_match:
                current_data["remote_hostname"] = device_id_match.group(1)
                continue

            # Parse Platform (for platform info)
            # e.g., "Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP"
            platform_match = re.search(
                r"Platform:\s*(.+?),\s*Capabilities:",
                line,
                re.IGNORECASE,
            )
            if platform_match:
                current_data["remote_platform"] = platform_match.group(1).strip()
                continue

            # Parse Interface and Port ID
            # e.g., "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24"
            interface_match = re.search(
                r"Interface:\s*([^,]+),\s*Port\s+ID\s*\(outgoing\s+port\):\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if interface_match:
                current_data["local_interface"] = interface_match.group(1).strip()
                current_data["remote_interface"] = interface_match.group(2).strip()
                continue

        # Don't forget the last neighbor entry
        if current_data and all(
            k in current_data
            for k in ["local_interface", "remote_hostname", "remote_interface"]
        ):
            results.append(
                NeighborData(
                    local_interface=current_data["local_interface"],
                    remote_hostname=current_data["remote_hostname"],
                    remote_interface=current_data["remote_interface"],
                    remote_platform=current_data.get("remote_platform"),
                )
            )

        return results


# Register the parser
parser_registry.register(CiscoIosNeighborParser())
