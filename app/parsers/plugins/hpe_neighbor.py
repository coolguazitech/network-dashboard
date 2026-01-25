"""
HPE Comware Neighbor Parser Plugin.

Parses 'display lldp neighbor-information' output from HPE Comware devices.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class HpeComwareNeighborParser(BaseParser[NeighborData]):
    """
    Parser for HPE Comware LLDP neighbor data.

    Parses output from: display lldp neighbor-information
    Tested with: HPE 5130 series
    """

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "uplink"
    command = "display lldp neighbor-information"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse HPE Comware LLDP neighbor output.

        Example output format:
        LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:
        LLDP neighbor index       : 1
        Chassis type              : MAC address
        Chassis ID                : 0012-3456-789a
        Port ID type              : Interface name
        Port ID                   : GigabitEthernet1/0/24
        Port description          : not advertised
        System name               : Core-Switch-01
        System description        : HPE Comware Platform Software
        System capabilities supported : Bridge, Router
        System capabilities enabled   : Bridge, Router
        Management address type       : IPv4
        Management address            : 10.0.1.1
        Expired time                  : 112s

        LLDP neighbor-information of port 2 [GigabitEthernet1/0/2]:
        LLDP neighbor index       : 1
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
                continue

            # Parse local port from header line
            # e.g., "LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:"
            local_port_match = re.search(
                r"LLDP\s+neighbor-information\s+of\s+port\s+\d+\s+\[([^\]]+)\]",
                line,
                re.IGNORECASE,
            )
            if local_port_match:
                # Save previous neighbor if exists
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

                current_data["local_interface"] = local_port_match.group(1)
                continue

            # Parse System name (e.g., "System name               : Core-Switch-01")
            system_name_match = re.search(
                r"System\s+name\s*:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if system_name_match:
                current_data["remote_hostname"] = system_name_match.group(1)
                continue

            # Parse Port ID (remote interface)
            # e.g., "Port ID                   : GigabitEthernet1/0/24"
            port_id_match = re.search(
                r"Port\s+ID\s*:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if port_id_match:
                current_data["remote_interface"] = port_id_match.group(1)
                continue

            # Parse System description (for platform info)
            # e.g., "System description        : HPE Comware Platform Software"
            system_desc_match = re.search(
                r"System\s+description\s*:\s*(.+)",
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
parser_registry.register(HpeComwareNeighborParser())
