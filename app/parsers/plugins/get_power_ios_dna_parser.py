"""
Parser for 'get_power_ios_dna' API.

Parses Cisco IOS `show environment power` output to extract power supply status.

Real CLI command: show environment power
Platforms: Catalyst 2960, 3560, 3750, 3850, 9200, 9300, 9500

=== ParsedData Model (DO NOT REMOVE) ===
class PowerData(ParsedData):
    ps_id: str                               # e.g. "PS1", "Power Supply 1"
    status: str                              # auto-normalized → OperationalStatus
    input_status: str | None = None          # optional
    output_status: str | None = None         # optional
    capacity_watts: float | None = None      # optional, >= 0
    actual_output_watts: float | None = None # optional, >= 0

Valid status values: ok, good, normal, online, active, fail, absent, unknown
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show environment power (or similar)
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class GetPowerIosDnaParser(BaseParser[PowerData]):
    """
    Parser for Cisco IOS ``show environment power`` output.

    Real CLI output (ref: ``show env all`` / ``show env power``)::

        SW  PID                 Serial#     Status           Sys Pwr  PoE Pwr  Watts
        --  ------------------  ----------  ---------------  -------  -------  -----
        1A  PWR-C1-350WAC       LIT2345ABCD Ok               Good     Good     350
        1B  Not Present

    Simpler Catalyst 2960/3560/3750 format::

        PS1 is OK
        PS2 is NOT PRESENT

    Alternative::

        Power Supply 1 is OK
        Power Supply 2 is NOT PRESENT

    Notes:
        - Status: OK, NOT OK, NOT PRESENT, FAULTY, etc.
        - Multiple format variants handled with fallback patterns.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_power_ios_dna"

    # Pattern: "PS1 is OK" or "PS2 is NOT OK"
    PS_IS_PATTERN = re.compile(
        r"^\s*(?P<ps_id>PS\d+)\s+is\s+(?P<status>.+?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Pattern: "Power Supply 1 is OK" or "Power Supply 2 is NOT PRESENT"
    POWER_SUPPLY_PATTERN = re.compile(
        r"^\s*Power\s+Supply\s+(?P<id>\d+)\s+is\s+(?P<status>.+?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Tabular pattern: "PS1    OK" (columns separated by whitespace)
    # Only match lines that look like "PS<num>  <status>" without "is" keyword
    TABLE_ROW_PATTERN = re.compile(
        r"^\s*(?P<ps_id>PS\d+)\s+(?P<status>OK|FAULTY|NOT\s+OK|NOT\s+PRESENT|ABSENT|NORMAL|FAIL)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    def parse(self, raw_output: str) -> list[PowerData]:
        results: list[PowerData] = []
        seen_ids: set[str] = set()

        # Pattern 1: "PS1 is OK" format
        for match in self.PS_IS_PATTERN.finditer(raw_output):
            ps_id = match.group("ps_id").upper()
            status = match.group("status").strip()
            if ps_id not in seen_ids:
                seen_ids.add(ps_id)
                results.append(PowerData(ps_id=ps_id, status=status))

        # Pattern 2: "Power Supply 1 is OK" format
        for match in self.POWER_SUPPLY_PATTERN.finditer(raw_output):
            ps_num = match.group("id")
            ps_id = f"PS{ps_num}"
            status = match.group("status").strip()
            if ps_id not in seen_ids:
                seen_ids.add(ps_id)
                results.append(PowerData(ps_id=ps_id, status=status))

        # Pattern 3: Tabular format "PS1  OK" (only if no previous matches)
        if not results:
            for match in self.TABLE_ROW_PATTERN.finditer(raw_output):
                ps_id = match.group("ps_id").upper()
                status = match.group("status").strip()
                if ps_id not in seen_ids:
                    seen_ids.add(ps_id)
                    results.append(PowerData(ps_id=ps_id, status=status))

        return results


# Register parser
parser_registry.register(GetPowerIosDnaParser())
