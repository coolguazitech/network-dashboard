"""
Cisco NX-OS Fan Status Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class CiscoNxosFanParser(BaseParser[FanStatusData]):
    """Parser for Cisco NX-OS Fan status."""

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "fan"
    command = "show environment fan"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        """
        Parse 'show environment fan' output.
        
        Example:
        Fan             Model                Hw     Status
        ---------------------------------------------------------------------------
        Fan1(Sys_Fan1)  NXA-FAN-30CFM-F      --     Ok
        Fan_in_PS1      --                   --     Ok
        """
        results = []
        
        # Regex to capture fan line
        # Group 1: Fan ID
        # Group 2: Model (optional)
        # Group 3: Status
        pattern = re.compile(
            r"^(\S+)\s+(.+?)\s+([A-Za-z]+)\s*$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            if line.startswith("Fan") or line.startswith("---") or not line:
                continue
                
            # Try splitting by whitespace first, as regex might be tricky with variable columns
            parts = line.split()
            if len(parts) >= 2:
                fan_id = parts[0]
                status = parts[-1] # Status is usually last
                
                # Filter out header row if not caught
                if fan_id == "Fan" and status == "Status":
                    continue
                    
                results.append(
                    FanStatusData(
                        fan_id=fan_id,
                        status=status,
                        speed_rpm=None,
                        speed_percent=None
                    )
                )
            
        return results


# Register parsers
parser_registry.register(CiscoNxosFanParser())
