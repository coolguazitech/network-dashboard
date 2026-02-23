"""
Parser for 'get_uplink_lldp_nxos_dna' API.

Parses Cisco NX-OS `show lldp neighbors detail` output to extract
LLDP neighbor details (remote hostname, interface, platform).

=== ParsedData Model (DO NOT REMOVE) ===
class NeighborData(ParsedData):
    local_interface: str                     # local port, e.g. "GigabitEthernet0/1"
    remote_hostname: str                     # neighbor device name
    remote_interface: str                    # neighbor port
    remote_platform: str | None = None       # optional platform description
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


class GetUplinkLldpNxosDnaParser(BaseParser[NeighborData]):
    """
    Parser for Cisco NX-OS ``show lldp neighbors detail`` output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_lldp_neighbors_detail.raw``)::

        Chassis id: 0026.980a.3c01
        Port id: Ethernet1/25
        Local Port id: Eth1/1
        Port Description: SERVER-ETH0
        System Name: SPINE-01
        System Description:
        Cisco Nexus Operating System (NX-OS) Software 9.3(8)
        Time remaining: 106 seconds
        System Capabilities: B, R
        Enabled Capabilities: B, R
        Management Address: 10.0.0.1

        Chassis id: 0026.980a.3c02
        Port id: Ethernet1/25
        Local Port id: Eth1/2
        System Name: SPINE-02
        System Description:
        Cisco Nexus Operating System (NX-OS) Software 9.3(8)
        Time remaining: 106 seconds

    Notes:
        - Blocks split by ``Chassis id:`` lookahead.
        - Required fields: Local Port id, Port id, System Name.
        - ``not advertised`` values are treated as missing.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_uplink_lldp_nxos_dna"

    # LLDP field patterns
    LOCAL_PORT_PATTERN = re.compile(
        r'^\s*Local Port id:\s*(?P<value>\S+)', re.MULTILINE
    )
    PORT_ID_PATTERN = re.compile(
        r'^\s*Port id:\s*(?P<value>\S+)', re.MULTILINE
    )
    SYSTEM_NAME_PATTERN = re.compile(
        r'^\s*System Name:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )
    SYSTEM_DESC_PATTERN = re.compile(
        r'^\s*System Description:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse NX-OS LLDP neighbor output into NeighborData records.

        Args:
            raw_output: Raw CLI output from `show lldp neighbors detail`

        Returns:
            List of NeighborData, one per discovered LLDP neighbor.
        """
        results: list[NeighborData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Split into blocks by 'Chassis id:' lookahead
        blocks = re.split(r'(?=Chassis id:)', raw_output)

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

        Returns None if required fields (Local Port id, Port id,
        System Name) are missing.
        """
        # Extract local interface (Local Port id) - required
        local_match = self.LOCAL_PORT_PATTERN.search(block)
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

        # Extract remote platform (System Description) - optional
        remote_platform: str | None = None
        desc_match = self.SYSTEM_DESC_PATTERN.search(block)
        if desc_match:
            desc = desc_match.group("value").strip()
            if desc and "not advertised" not in desc.lower():
                remote_platform = desc

        return NeighborData(
            local_interface=local_interface,
            remote_hostname=remote_hostname,
            remote_interface=remote_interface,
            remote_platform=remote_platform,
        )


# Register parser
parser_registry.register(GetUplinkLldpNxosDnaParser())
