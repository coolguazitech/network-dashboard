"""
Parser for 'get_channel_group_hpe_fna' API.

Parses HPE Comware `display link-aggregation summary` tabular output
to extract LAG interface, status, protocol, and member details.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class GetChannelGroupHpeFnaParser(BaseParser[PortChannelData]):
    """
    Parser for HPE Comware ``display link-aggregation summary`` output.

    Real CLI output (ref: NTC-templates ``hp_comware_display_link-aggregation_verbose.raw``,
    summary variant):
    ```
    AggID   Interface   Link   Attribute   Mode   Members
    1       BAGG1       UP     A           LACP   HGE1/0/25(S) HGE1/0/26(S)
    2       BAGG2       DOWN   A           STATIC HGE1/0/27(U)
    ```

    Fields:
    - AggID: Aggregation group number (ignored, we use Interface)
    - Interface: Aggregate interface name (e.g. BAGG1)
    - Link: UP or DOWN
    - Attribute: A (auto) etc. (ignored)
    - Mode: LACP, STATIC, etc.
    - Members: Space-separated list of member ports with (S)/(U) suffixes
      - (S) = Selected = up
      - (U) = Unselected = down
    """

    device_type = DeviceType.HPE
    command = "get_channel_group_hpe_fna"

    # Match a data row in the summary table.
    # Group: AggID  Interface  Link  Attribute  Mode  Members...
    ROW_PATTERN = re.compile(
        r'^\s*(?P<agg_id>\d+)\s+'
        r'(?P<interface>\S+)\s+'
        r'(?P<link>UP|DOWN)\s+'
        r'(?P<attribute>\S+)\s+'
        r'(?P<mode>\S+)\s+'
        r'(?P<members>.+?)\s*$',
        re.MULTILINE | re.IGNORECASE,
    )

    # Extract individual member port: InterfaceName(S) or InterfaceName(U)
    MEMBER_PATTERN = re.compile(r'(?P<intf>\S+?)\((?P<flag>[SU])\)')

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse HPE link-aggregation summary output into PortChannelData records.

        Args:
            raw_output: Raw CLI output from `display link-aggregation summary`

        Returns:
            List of PortChannelData, one per aggregate interface.
        """
        results: list[PortChannelData] = []

        if not raw_output or not raw_output.strip():
            return results

        for row_match in self.ROW_PATTERN.finditer(raw_output):
            record = self._parse_row(row_match)
            if record is not None:
                results.append(record)

        return results

    def _parse_row(self, row_match: re.Match[str]) -> PortChannelData | None:
        """
        Parse a single table row into a PortChannelData record.

        Returns None if the row cannot be parsed.
        """
        interface_name = row_match.group("interface").strip()
        link_status = row_match.group("link").strip().lower()
        mode = row_match.group("mode").strip()
        members_text = row_match.group("members").strip()

        # Determine protocol from Mode column
        protocol = self._normalize_protocol(mode)

        # Parse member ports and their statuses
        members: list[str] = []
        member_status: dict[str, str] = {}

        for member_match in self.MEMBER_PATTERN.finditer(members_text):
            intf = member_match.group("intf")
            flag = member_match.group("flag").upper()
            members.append(intf)
            # (S) = Selected = up, (U) = Unselected = down
            member_status[intf] = "up" if flag == "S" else "down"

        return PortChannelData(
            interface_name=interface_name,
            status=link_status,
            protocol=protocol,
            members=members,
            member_status=member_status if member_status else None,
        )

    @staticmethod
    def _normalize_protocol(mode: str) -> str:
        """Convert HPE Mode value to aggregation protocol string."""
        mode_lower = mode.strip().lower()
        if mode_lower == "lacp":
            return "lacp"
        if mode_lower == "static":
            return "static"
        # Any other mode treated as none
        return "none"


# Register parser
parser_registry.register(GetChannelGroupHpeFnaParser())
