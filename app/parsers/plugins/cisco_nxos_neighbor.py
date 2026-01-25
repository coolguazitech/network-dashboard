"""
Cisco NX-OS Neighbor Parser Plugin.

Parses 'show lldp neighbors detail' output from Cisco NX-OS devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class CiscoNxosNeighborParser(BaseParser[NeighborData]):
    """
    Parser for Cisco NX-OS LLDP neighbor data.

    Parses output from: show lldp neighbors detail
    Tested with: Nexus 9000 series
    """

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "uplink"
    command = "show lldp neighbors detail"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse NX-OS LLDP neighbor output.

        Example output format:
        Chassis id: 0012.3456.789a
        Port id: Ethernet1/1
        Local Port id: Eth1/49
        Port Description: not advertised
        System Name: spine-01.example.com
        System Description: Cisco Nexus Operating System (NX-OS) Software
        Time remaining: 112 seconds
        System Capabilities: B, R
        Enabled Capabilities: B, R
        Management Address: 10.0.1.1
        Vlan ID: not advertised

        Chassis id: 0012.3456.789b
        Port id: Ethernet1/2
        Local Port id: Eth1/50
        System Name: spine-02.example.com
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

            # Skip empty lines
            if not line:
                # If we have accumulated data, save it
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

            # Parse Local Port id (e.g., "Local Port id: Eth1/49")
            local_port_match = re.search(
                r"Local\s+Port\s+id:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if local_port_match:
                local_port = local_port_match.group(1)
                # Normalize Eth to Ethernet
                if local_port.startswith("Eth") and not local_port.startswith("Ethernet"):
                    local_port = "Ethernet" + local_port[3:]
                current_data["local_interface"] = local_port
                continue

            # Parse System Name (e.g., "System Name: spine-01.example.com")
            system_name_match = re.search(
                r"System\s+Name:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if system_name_match:
                current_data["remote_hostname"] = system_name_match.group(1)
                continue

            # Parse Port id (remote interface) (e.g., "Port id: Ethernet1/1")
            # Note: This must come after "Local Port id" check
            port_id_match = re.search(
                r"^Port\s+id:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if port_id_match:
                port_id = port_id_match.group(1)
                # Normalize Eth to Ethernet
                if port_id.startswith("Eth") and not port_id.startswith("Ethernet"):
                    port_id = "Ethernet" + port_id[3:]
                current_data["remote_interface"] = port_id
                continue

            # Parse System Description (for platform info)
            # e.g., "System Description: Cisco Nexus Operating System (NX-OS) Software"
            system_desc_match = re.search(
                r"System\s+Description:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            if system_desc_match:
                current_data["remote_platform"] = system_desc_match.group(1).strip()
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
parser_registry.register(CiscoNxosNeighborParser())
