"""
Parser for 'get_channel_group_ios_fna' API.

Parses Cisco IOS/IOS-XE `show etherchannel summary` output to extract
port-channel interface, status, protocol, and member details.

=== ParsedData Model (DO NOT REMOVE) ===
class PortChannelData(ParsedData):
    interface_name: str                      # e.g. "Po1", "Bridge-Aggregation1"
    status: str                              # auto-normalized → LinkStatus (up/down/unknown)
    members: list[str]                       # member interface names
    member_status: dict[str, str] | None     # {interface: "up"|"down"}, optional
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show etherchannel summary
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class GetChannelGroupIosFnaParser(BaseParser[PortChannelData]):
    """
    Parser for Cisco IOS/IOS-XE ``show etherchannel summary`` output.

    Real CLI output (ref: NTC-templates ``cisco_ios_show_etherchannel_summary.raw``):
    ```
    Flags:  D - down        P - bundled in port-channel
            I - stand-alone s - suspended
            H - Hot-standby (LACP only)
            R - Layer3      S - Layer2
            U - in use      N - not in use, no aggregation
            f - failed to allocate aggregator

    Number of channel-groups in use: 2
    Number of aggregators:           2

    Group  Port-channel  Protocol    Ports
    ------+-------------+-----------+-----------------------------------------------
    1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
    7      Po7(SD)       -           Gi1/0/5(D)  Gi1/0/6(I)
    ```

    Notes:
    - Port-channel status flags: S=Layer2, R=Layer3, U=Up, D=Down
      - (SU) or (RU) = up; (SD) or (RD) = down
    - Member status flags: P=bundled(up), D=down, I=standalone(down),
      s=suspended(down), H=hot-standby(down), w=waiting(down), f=failed(down)
    - Protocol: LACP, PAgP, or '-' (static/manual)
    - Members can wrap to continuation lines (indented)
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_channel_group_ios_fna"

    # Match a group start line: group_num  PoN(flags)  protocol  members...
    GROUP_LINE_PATTERN = re.compile(
        r'^\s*(?P<group>\d+)\s+'
        r'(?P<po_name>Po\d+)\((?P<flags>[A-Za-z]+)\)\s+'
        r'(?P<protocol>LACP|PAgP|-)\s*'
        r'(?P<rest>.*)',
        re.MULTILINE,
    )

    # Extract individual member port: InterfaceName(Flag)
    MEMBER_PATTERN = re.compile(r'(?P<intf>\S+?)\((?P<flag>\w+)\)')

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse IOS etherchannel summary output into PortChannelData records.

        Args:
            raw_output: Raw CLI output from `show etherchannel summary`

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
                # Continuation line: heavily indented, contains member ports
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

        P (bundled) = up; D (down), I (standalone), s (suspended),
        H (hot-standby), w (waiting), f (failed) = down.
        """
        return "up" if flag in ("P", "bndl") else "down"

    @staticmethod
    def _normalize_protocol(proto: str) -> str:
        """Convert protocol string to aggregation protocol value."""
        p = proto.strip().upper()
        if p == "LACP":
            return "lacp"
        if p == "PAGP":
            return "pagp"
        # '-' means manual/static EtherChannel (channel-group mode on)
        return "static"


# Register parser
parser_registry.register(GetChannelGroupIosFnaParser())
