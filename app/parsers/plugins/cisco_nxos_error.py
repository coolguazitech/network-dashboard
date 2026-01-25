"""
Cisco NX-OS Interface Error Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class CiscoNxosErrorParser(BaseParser[InterfaceErrorData]):
    """Parser for Cisco NX-OS interface error counters."""

    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "error_count"
    command = "show interface counters errors"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        """
        Parse 'show interface counters errors' output.
        
        Example:
        --------------------------------------------------------------------------------
        Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        --------------------------------------------------------------------------------
        Eth1/1                0          0          0          0          0           0
        Eth1/2               10          5          0          0          0           0
        """
        results = []
        
        # Regex to capture error line
        # Group 1: Interface
        # Group 2-N: Error counts (we only care about some)
        # Note: Columns may vary slightly, but usually:
        # Port, Align-Err, FCS-Err, Xmit-Err, Rcv-Err, UnderSize, OutDiscards
        pattern = re.compile(
            r"^([A-Za-z0-9\/]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface = match.group(1)
            # align_err = int(match.group(2))
            fcs_err = int(match.group(3))
            # xmit_err = int(match.group(4))
            rcv_err = int(match.group(5))
            # undersize = int(match.group(6))
            # out_discards = int(match.group(7))
            
            # For simplicity, we map:
            # crc_errors = fcs_err
            # input_errors = rcv_err
            # output_errors = xmit_err (simplified)
            
            # Only include if there are errors (optional, but saves space)
            # Or always include to show status? Usually always include for validation.
            
            results.append(
                InterfaceErrorData(
                    interface_name=interface,
                    crc_errors=fcs_err,
                    input_errors=rcv_err,
                    # output_errors=xmit_err,
                    # collisions=0, # Not in this command usually
                    # giants=0,
                    # runts=undersize
                )
            )
            
        return results


# Register parsers
parser_registry.register(CiscoNxosErrorParser())
