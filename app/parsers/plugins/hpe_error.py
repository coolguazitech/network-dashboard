"""
HPE Comware Interface Error Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class HpeErrorParser(BaseParser[InterfaceErrorData]):
    """Parser for HPE Comware interface error counters."""

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "error_count"
    command = "display counters error"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        """
        Parse 'display counters error' output.
        
        Example:
        Interface            Input(errs)       Output(errs)
        GE1/0/1                        0                  0
        GE1/0/2                        0                  0
        """
        results = []
        
        # Regex to capture error line
        # Group 1: Interface
        # Group 2: Input errors
        # Group 3: Output errors
        pattern = re.compile(
            r"^([A-Za-z0-9\/]+)\s+(\d+)\s+(\d+)",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface = match.group(1)
            input_err = int(match.group(2))
            output_err = int(match.group(3))
            
            results.append(
                InterfaceErrorData(
                    interface_name=interface,
                    crc_errors=0, # HPE output might be simplified here
                    input_errors=input_err,
                    output_errors=output_err,
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpeErrorParser())
