"""
Cisco NX-OS Power Supply Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class CiscoNxosPowerParser(BaseParser[PowerData]):
    """Parser for Cisco NX-OS Power Supply status."""

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "power"
    command = "show environment power"

    def parse(self, raw_output: str) -> list[PowerData]:
        """
        Parse 'show environment power' output.
        
        Example:
        Power                              Actual        Total
        Supply    Model                    Output     Capacity    Status
                                           (Watts)     (Watts)
        -------  -------------------  -----------  -----------  --------------
        1        NXA-PAC-650W-PI              124          650     Ok
        2        NXA-PAC-650W-PI              132          650     Ok
        """
        results = []
        
        # Regex for table rows
        # 1        NXA-PAC-650W-PI              124          650     Ok
        # Group 1: ID
        # Group 2: Model
        # Group 3: Output
        # Group 4: Capacity
        # Group 5: Status
        pattern = re.compile(
            r"^(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(.+)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            # Skip header lines
            if line.startswith("Power") or line.startswith("Supply") or line.startswith("---") or line.startswith("Voltage"):
                continue
                
            match = pattern.match(line)
            if not match:
                continue
                
            ps_id = match.group(1)
            output = float(match.group(3))
            capacity = float(match.group(4))
            status = match.group(5).strip()
            
            results.append(
                PowerData(
                    ps_id=ps_id,
                    status=status,
                    capacity_watts=capacity,
                    actual_output_watts=output,
                    input_status=None,  # NXOS output usually implies input ok if status is ok
                    output_status=status
                )
            )
            
        return results


# Register parsers
parser_registry.register(CiscoNxosPowerParser())
