"""
Generic Ping Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, PingData
from app.parsers.registry import parser_registry


# Note: Registering for multiple vendors/platforms might require multiple classes 
# or a more flexible registration. For now, we register for generic usage.
# Since we can't register "Generic", we might need to handle this differently in DataCollectionService.
# But here we implement specific ones for consistency.

class CiscoNxosPingParser(BaseParser[PingData]):
    """Parser for Cisco NX-OS Ping."""
    vendor = VendorType.CISCO
    platform = PlatformType.CISCO_NXOS
    indicator_type = "ping"
    command = "ping" # Placeholder

    def parse(self, raw_output: str) -> list[PingData]:
        return self._parse_generic(raw_output)

    def _parse_generic(self, raw_output: str) -> list[PingData]:
        # Linux/Cisco style: 5 packets transmitted, 5 packets received, 0.0% packet loss
        # Windows style: Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)
        
        success_rate = 0.0
        is_reachable = False
        avg_rtt = None
        
        # Match packet loss
        loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", raw_output)
        if loss_match:
            loss_pct = float(loss_match.group(1))
            success_rate = 100.0 - loss_pct
        else:
            # Try Windows style
            loss_match_win = re.search(r"\((\d+)% loss\)", raw_output)
            if loss_match_win:
                loss_pct = float(loss_match_win.group(1))
                success_rate = 100.0 - loss_pct
        
        # Match RTT (min/avg/max)
        # round-trip min/avg/max = 1.1/2.2/3.3 ms
        rtt_match = re.search(r"min/avg/max.*?=\s*[\d\.]+/([\d\.]+)/[\d\.]+", raw_output)
        if rtt_match:
            avg_rtt = float(rtt_match.group(1))
            
        if success_rate > 0:
            is_reachable = True
            
        return [
            PingData(
                target="self", # Usually pinging the device itself
                is_reachable=is_reachable,
                success_rate=success_rate,
                avg_rtt_ms=avg_rtt
            )
        ]

class HpePingParser(CiscoNxosPingParser):
    """Parser for HPE Ping."""
    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "ping"
    command = "ping"


# Register parsers
parser_registry.register(CiscoNxosPingParser())
parser_registry.register(HpePingParser())
