"""
Parser for 'get_fan_ios_dna' API.

Parses Cisco IOS ``show environment`` fan output to extract fan status.
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class GetFanIosDnaParser(BaseParser[FanStatusData]):
    """
    Parser for Cisco IOS ``show environment`` / ``show env all`` fan output.

    Real CLI output (ref: Cisco IOS ``show env all``)::

        FAN 1 is OK
        FAN 2 is OK
        FAN PS-1 is OK
        FAN PS-2 is NOT OK
        SYSTEM FAN is OK

    Some platforms use alternative format::

        SYSTEM FANS:
        FAN is OK

    Notes:
        - Matches ``<label> is <status>`` lines where label contains "FAN".
        - Status: OK, NOT OK, NOT PRESENT, etc.
        - fan_id preserves the original label (e.g. "FAN 1", "FAN PS-1").
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_fan_ios_dna"

    # Matches lines like:
    #   "FAN 1 is OK"
    #   "SYSTEM FAN is OK"
    #   "FAN PS-1 is NOT OK"
    #   "Fan_in_PS-1 is Ok"
    # Captures everything before "is" as fan_id, everything after as status.
    FAN_LINE_PATTERN = re.compile(
        r"^(.+?)\s+is\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE
    )

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results: list[FanStatusData] = []

        if not raw_output or not raw_output.strip():
            return results

        for match in self.FAN_LINE_PATTERN.finditer(raw_output):
            fan_id = match.group(1).strip()
            status = match.group(2).strip()

            # Only process lines that look like fan entries
            # (contain "FAN" somewhere in the identifier)
            if "fan" not in fan_id.lower():
                continue

            # Skip separator or header lines
            if fan_id.startswith("-") or fan_id.startswith("="):
                continue

            results.append(
                FanStatusData(
                    fan_id=fan_id,
                    status=status,
                    speed_rpm=None,
                    speed_percent=None,
                )
            )

        return results


# Register parser
parser_registry.register(GetFanIosDnaParser())
