"""
HPE Comware Port-Channel Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class HpePortChannelParser(BaseParser[PortChannelData]):
    """Parser for HPE Comware Port-Channel (Bridge-Aggregation) status."""

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "port_channel"
    command = "display link-aggregation verbose"  # or summary

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse 'display link-aggregation summary' output.
        
        Example output:
        Aggregation Interface: Bridge-Aggregation1
        Aggregation Mode: Dynamic
        Loadsharing Type: Shar
        System ID: 0x8000, 3822-d698-0c00
        Local:
          Port             Status  Priority Oper-Key  Flag
        --------------------------------------------------------------------------------
          GE1/0/1          S       32768    1         {ACDEF}
          GE1/0/2          S       32768    1         {ACDEF}
        
        Or summary format:
        AggID   Interface   Link   Attribute   Mode   Members
        1       BAGG1       UP     A           LACP   GE1/0/1(S) GE1/0/2(S)
        """
        results = []
        
        # Strategy: Parse summary format as it's more common for high-level checks
        # Regex for summary line
        # Group 1: AggID
        # Group 2: Interface Name
        # Group 3: Link Status
        # Group 4: Attribute
        # Group 5: Mode
        # Group 6: Members string
        pattern = re.compile(
            r"^(\d+)\s+([A-Za-z0-9_-]+)\s+(UP|DOWN)\s+(\w+)\s+(\w+)\s+(.*)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface_name = match.group(2)
            status = match.group(3)
            mode = match.group(5)
            members_str = match.group(6)
            
            # Protocol inference
            protocol = "LACP" if "LACP" in mode or "Dynamic" in mode else "STATIC"
            
            # Parse Members
            # GE1/0/1(S) GE1/0/2(S)
            members = []
            member_status = {}
            
            member_tokens = members_str.split()
            for token in member_tokens:
                m_match = re.match(r"([^(]+)\(([^)]+)\)", token)
                if m_match:
                    m_name = m_match.group(1)
                    m_code = m_match.group(2)
                    members.append(m_name)
                    # S = Selected (Active/Up), U = Unselected (Standby/Down)
                    member_status[m_name] = "UP" if "S" in m_code else "DOWN"
                else:
                    members.append(token)
                    member_status[token] = "UNKNOWN"
            
            results.append(
                PortChannelData(
                    interface_name=interface_name,
                    status=status,
                    protocol=protocol,
                    members=members,
                    member_status=member_status
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpePortChannelParser())
