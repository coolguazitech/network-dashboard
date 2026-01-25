"""
HPE Comware Fan Status Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class HpeFanParser(BaseParser[FanStatusData]):
    """Parser for HPE Comware Fan status."""

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "fan"
    command = "display fan"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        """
        Parse 'display fan' output.
        
        Example:
         Slot 1:
         FanID    Status      Direction
         1        Normal      Back-to-front
        """
        results = []
        
        # Regex to capture fan line
        # Group 1: Fan ID
        # Group 2: Status
        # Group 3: Direction (optional)
        pattern = re.compile(
            r"^\s*(\d+)\s+(\S+)\s+(.+?)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            # Skip headers
            if line.startswith("Slot") or line.startswith("FanID"):
                continue
                
            match = pattern.match(line)
            if not match:
                continue
                
            fan_id = match.group(1)
            status = match.group(2)
            
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
parser_registry.register(HpeFanParser())
