"""
Cisco NX-OS Port-Channel Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class CiscoNxosPortChannelParser(BaseParser[PortChannelData]):
    """Parser for Cisco NX-OS Port-Channel status."""

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "port_channel"
    command = "show port-channel summary"

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse 'show port-channel summary' output.
        
        Example output:
        --------------------------------------------------------------------------------
        Group Port-       Type     Protocol  Member Ports
              Channel
        --------------------------------------------------------------------------------
        1     Po1(SU)     Eth      LACP      Eth1/1(P)    Eth1/2(P)
        10    Po10(SD)    Eth      LACP      Eth1/10(D)
        """
        results = []
        
        # Regex to capture Port-Channel line
        # Group 1: ID
        # Group 2: Name + Status (e.g. Po1(SU))
        # Group 3: Type
        # Group 4: Protocol
        # Group 5: Members string
        pattern = re.compile(
            r"^(\d+)\s+([A-Za-z0-9\(\)]+)\s+(\w+)\s+(\w+|-+)\s+(.*)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            pc_name_status = match.group(2)
            protocol = match.group(4)
            members_str = match.group(5)
            
            # Parse PC Name and Status
            # Po1(SU) -> Po1, SU
            pc_match = re.match(r"([^(]+)\(([^)]+)\)", pc_name_status)
            if pc_match:
                pc_name = pc_match.group(1)
                pc_status_code = pc_match.group(2)
                pc_status = "UP" if "U" in pc_status_code else "DOWN"
            else:
                pc_name = pc_name_status
                pc_status = "UNKNOWN"
                
            # Parse Members
            # Eth1/1(P) Eth1/2(P)
            members = []
            member_status = {}
            
            # Simple split by space, then parse each member
            member_tokens = members_str.split()
            for token in member_tokens:
                m_match = re.match(r"([^(]+)\(([^)]+)\)", token)
                if m_match:
                    m_name = m_match.group(1)
                    m_code = m_match.group(2)
                    members.append(m_name)
                    # P = Up in port-channel, D = Down
                    member_status[m_name] = "UP" if "P" in m_code else "DOWN"
                else:
                    members.append(token)
                    member_status[token] = "UNKNOWN"
            
            results.append(
                PortChannelData(
                    interface_name=pc_name,
                    status=pc_status,
                    protocol=protocol if protocol != "-" else None,
                    members=members,
                    member_status=member_status
                )
            )
            
        return results


# Register the parser
parser_registry.register(CiscoNxosPortChannelParser())
