"""
Parser for 'get_uplink_hpe_fna' API.

Parses HPE Comware `display lldp neighbor-information` output to extract
LLDP neighbor details (remote hostname, interface, platform).

=== ParsedData Model (DO NOT REMOVE) ===
class NeighborData(ParsedData):
    local_interface: str                     # local port, e.g. "GigabitEthernet0/1"
    remote_hostname: str                     # neighbor device name
    remote_interface: str                    # neighbor port
    remote_platform: str | None = None       # optional platform description
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display lldp neighbor-information list
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class GetUplinkHpeFnaParser(BaseParser[NeighborData]):
    """
    Parser for HPE Comware ``display lldp neighbor-information`` output.

    The real ``display lldp neighbor-information list`` returns a tabular summary::

        System Name  Local Interface         Chassis ID          Port ID
        CORE-SW-01   GigabitEthernet1/0/25   000c-29aa-bb01      HGE1/0/1
        CORE-SW-02   GigabitEthernet1/0/26   000c-29aa-bb02      HGE1/0/2

    The FNA API may return the verbose format instead
    (ref: NTC-templates ``hp_comware_display_lldp_neighbor-information_verbose.raw``)::

        LLDP neighbor-information of port 25[GigabitEthernet1/0/25]:
          Neighbor index                   : 1
          Update time                      : 0 days, 0 hours, 1 minutes, 30 seconds
          Chassis type                     : MAC address
          Chassis ID                       : 000c-29aa-bb01
          Port ID type                     : Interface name
          Port ID                          : HundredGigE1/0/1
          Port description                 : uplink
          System name                      : CORE-SW-01
          System description               : HPE Comware Platform Software,
          Software Version 7.1.070, Release 6635P07
          System capabilities supported    : Bridge, Router
          System capabilities enabled      : Bridge, Router
          Management address type          : IPv4
          Management address               : 10.0.0.1

        LLDP neighbor-information of port 26[GigabitEthernet1/0/26]:
          Chassis ID                       : 000c-29aa-bb02
          Port ID                          : HundredGigE1/0/2
          System name                      : CORE-SW-02
          System description               : HPE Comware Platform Software

    Notes:
        - This parser handles the **verbose** (key-value block) format.
        - Blocks split by ``LLDP neighbor-information of port N[IntfName]:``.
        - Local interface extracted from ``[IntfName]`` in header.
        - Required: System name, Port ID. System description is optional.
        - If FNA returns the list (tabular) format, parser may need adjustment.
    """

    device_type = DeviceType.HPE
    command = "get_uplink_hpe_fna"

    # Match block header to extract local interface name from brackets
    BLOCK_HEADER_PATTERN = re.compile(
        r'LLDP neighbor-information of port\s+\d+\s*\[(?P<local_intf>[^\]]+)\]',
        re.IGNORECASE,
    )

    # Key-value patterns for fields within each block
    SYSTEM_NAME_PATTERN = re.compile(
        r'^\s*System name\s*:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )
    PORT_ID_PATTERN = re.compile(
        r'^\s*Port ID\s*:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )
    SYSTEM_DESC_PATTERN = re.compile(
        r'^\s*System description\s*:\s*(?P<value>.+?)\s*$', re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse HPE LLDP neighbor output into NeighborData records.

        Args:
            raw_output: Raw CLI output from `display lldp neighbor-information`

        Returns:
            List of NeighborData, one per discovered LLDP neighbor.
        """
        results: list[NeighborData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Split into blocks by looking for "LLDP neighbor-information of port"
        blocks = self._split_into_blocks(raw_output)

        for block in blocks:
            neighbor = self._parse_block(block)
            if neighbor is not None:
                results.append(neighbor)

        return results

    def _split_into_blocks(self, output: str) -> list[str]:
        """
        Split the full output into individual neighbor blocks.

        Each block starts with 'LLDP neighbor-information of port'.
        """
        header_matches = list(self.BLOCK_HEADER_PATTERN.finditer(output))
        if not header_matches:
            return []

        blocks: list[str] = []
        for i, match in enumerate(header_matches):
            start = match.start()
            if i + 1 < len(header_matches):
                end = header_matches[i + 1].start()
            else:
                end = len(output)
            blocks.append(output[start:end])

        return blocks

    def _parse_block(self, block: str) -> NeighborData | None:
        """
        Parse a single LLDP neighbor block.

        Returns None if required fields (local_interface, remote_hostname,
        remote_interface) are missing.
        """
        # Extract local interface from block header
        header_match = self.BLOCK_HEADER_PATTERN.search(block)
        if not header_match:
            return None
        local_interface = header_match.group("local_intf").strip()

        # Extract remote hostname (System name) - required
        system_name_match = self.SYSTEM_NAME_PATTERN.search(block)
        if not system_name_match:
            return None
        remote_hostname = system_name_match.group("value").strip()
        if not remote_hostname:
            return None

        # Extract remote interface (Port ID) - required
        port_id_match = self.PORT_ID_PATTERN.search(block)
        if not port_id_match:
            return None
        remote_interface = port_id_match.group("value").strip()
        if not remote_interface:
            return None

        # Extract remote platform (System description) - optional
        remote_platform: str | None = None
        system_desc_match = self.SYSTEM_DESC_PATTERN.search(block)
        if system_desc_match:
            desc = system_desc_match.group("value").strip()
            if desc:
                remote_platform = desc

        return NeighborData(
            local_interface=local_interface,
            remote_hostname=remote_hostname,
            remote_interface=remote_interface,
            remote_platform=remote_platform,
        )


# Register parser
parser_registry.register(GetUplinkHpeFnaParser())
