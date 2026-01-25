"""
HPE Comware Power Supply Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class HpePowerParser(BaseParser[PowerData]):
    """Parser for HPE Comware Power Supply status."""

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "power"
    command = "display power"

    def parse(self, raw_output: str) -> list[PowerData]:
        """
        Parse 'display power' output.
        
        Example:
         Slot 1:
         PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
         1       Normal   AC     --          --          --        Back-to-front
         2       Normal   AC     --          --          --        Back-to-front
        """
        results = []
        
        # Regex for table rows
        # 1       Normal   AC     --          --          --        Back-to-front
        # Group 1: ID
        # Group 2: State
        # Group 3: Mode
        # Group 4: Current
        # Group 5: Voltage
        # Group 6: Power
        pattern = re.compile(
            r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            match = pattern.match(line)
            if not match:
                continue
                
            ps_id = match.group(1)
            state = match.group(2)
            
            # Helper to parse float or None
            def parse_float(val: str) -> float | None:
                if val == "--" or not val:
                    return None
                try:
                    return float(val)
                except ValueError:
                    return None
            
            actual_power = parse_float(match.group(6))
            
            results.append(
                PowerData(
                    ps_id=ps_id,
                    status=state,
                    capacity_watts=None,  # HPE output often doesn't show total capacity here
                    actual_output_watts=actual_power,
                    input_status=state,
                    output_status=state
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpePowerParser())
