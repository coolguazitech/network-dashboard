"""
Parser for 'get_channel_group_nxos_fna' API.

Parses Cisco NX-OS `show port-channel summary` output to extract
port-channel interface, status, protocol, and member details.

=== ParsedData Model (DO NOT REMOVE) ===
class PortChannelData(ParsedData):
    interface_name: str                      # e.g. "Po1", "Bridge-Aggregation1"
    status: str                              # auto-normalized → LinkStatus (up/down/unknown)
    members: list[str]                       # member interface names
    member_status: dict[str, str] | None     # {interface: "up"|"down"}, optional
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show port-channel summary
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class GetChannelGroupNxosFnaParser(BaseParser[PortChannelData]):
    """
    Parser for Cisco NX-OS ``show port-channel summary`` output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_port-channel_summary.raw``):
    ```
    Flags:  D - Down        P - Up in port-channel (members)
            I - Individual  H - Hot-standby (LACP only)
            s - Suspended   r - Module-removed
            S - Switched    R - Routed
            U - Up (port-channel)
            M - Not in use. Min-links not met
    --------------------------------------------------------------------------------
    Group Port-       Type     Protocol  Member Ports
          Channel
    --------------------------------------------------------------------------------
    1     Po1(SU)     Eth      LACP      Eth1/25(P)    Eth1/26(P)
    135   Po135(SD)   Eth      NONE      --
    811   Po811(RU)   Eth      LACP      Eth15/8(P)   Eth15/28(P)  Eth16/8(P)
                                         Eth16/28(P)
    ```

    Notes:
    - Port-channel status flags: S=Switched(L2), R=Routed(L3), U=Up, D=Down
      - (SU) or (RU) = up; (SD) or (RD) = down
    - Member status flags: P=up-in-port-channel(up), D=down, I=individual(down),
      s=suspended(down), H=hot-standby(down), r=module-removed(down)
    - Protocol: LACP or NONE (static)
    - Empty member list shown as '--'
    - Members can wrap to continuation lines (indented)
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_channel_group_nxos_fna"

    # Match a group start line: Group  PoN(flags)  Type  Protocol  Members...
    GROUP_LINE_PATTERN = re.compile(
        r'^\s*(?P<group>\d+)\s+'
        r'(?P<po_name>Po\d+)\((?P<flags>[A-Za-z]+)\)\s+'
        r'(?P<type>\w+)\s+'
        r'(?P<protocol>LACP|NONE)\s*'
        r'(?P<rest>.*)',
        re.MULTILINE,
    )

    # Extract individual member port: EthX/Y(Flag) or EthX/Y/Z(Flag)
    MEMBER_PATTERN = re.compile(r'(?P<intf>Eth[\d/]+)\((?P<flag>\w+)\)')

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse NX-OS port-channel summary output into PortChannelData records.

        Args:
            raw_output: Raw CLI output from `show port-channel summary`

        Returns:
            List of PortChannelData, one per port-channel.
        """
        results: list[PortChannelData] = []

        if not raw_output or not raw_output.strip():
            return results

        lines = raw_output.splitlines()
        current_group: dict[str, str] | None = None
        current_ports_text = ""

        for line in lines:
            # Skip separator lines (----)
            if re.match(r'^\s*-{4,}\s*$', line):
                continue

            group_match = self.GROUP_LINE_PATTERN.match(line)
            if group_match:
                # Finalize previous group
                if current_group is not None:
                    record = self._build_record(current_group, current_ports_text)
                    results.append(record)

                current_group = {
                    "po_name": group_match.group("po_name"),
                    "flags": group_match.group("flags"),
                    "protocol": group_match.group("protocol"),
                }
                current_ports_text = group_match.group("rest")
            elif current_group is not None:
                # Continuation line: indented, contains member ports
                stripped = line.strip()
                if stripped and self.MEMBER_PATTERN.search(stripped):
                    current_ports_text += " " + stripped

        # Finalize last group
        if current_group is not None:
            record = self._build_record(current_group, current_ports_text)
            results.append(record)

        return results

    def _build_record(self, group: dict[str, str], ports_text: str) -> PortChannelData:
        """Build a PortChannelData from parsed group info and member ports text."""
        members: list[str] = []
        member_status: dict[str, str] = {}

        # '--' means no member ports assigned
        if ports_text.strip() != "--":
            for member_match in self.MEMBER_PATTERN.finditer(ports_text):
                intf = member_match.group("intf")
                flag = member_match.group("flag")
                members.append(intf)
                member_status[intf] = self._member_flag_to_status(flag)

        return PortChannelData(
            interface_name=group["po_name"],
            status=self._flags_to_status(group["flags"]),
            members=members,
            member_status=member_status if member_status else None,
        )

    @staticmethod
    def _flags_to_status(flags: str) -> str:
        """
        Convert port-channel flags to link status.

        (SU) or (RU) = up (U present); (SD) or (RD) = down.
        """
        return "up" if "U" in flags else "down"

    @staticmethod
    def _member_flag_to_status(flag: str) -> str:
        """
        Convert member port flag to link status.

        P (up in port-channel) = up; D, I, s, H, r = down.
        """
        return "up" if flag == "P" else "down"

    @staticmethod
    def _normalize_protocol(proto: str) -> str:
        """Convert protocol string to aggregation protocol value."""
        if proto.upper() == "LACP":
            return "lacp"
        # NONE means static/manual port-channel
        return "static"


# Register parser
parser_registry.register(GetChannelGroupNxosFnaParser())
