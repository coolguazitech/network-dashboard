"""
Parser for 'get_power_hpe_dna' API.

Parses HPE Comware `display power` output to extract power supply status
for each slot/power-supply combination.

Real CLI command: display power
Platforms: HPE Comware (5710, 5940, 5945, 5130, etc.)

=== ParsedData Model (DO NOT REMOVE) ===
class PowerData(ParsedData):
    ps_id: str                               # e.g. "PS1", "Power Supply 1"
    status: str                              # auto-normalized → OperationalStatus

Valid status values: ok, good, normal, online, active, fail, absent, unknown
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display power
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class GetPowerHpeDnaParser(BaseParser[PowerData]):
    """
    Parser for HPE Comware ``display power`` output.

    Real CLI output (ref: HPE Comware CLI Reference)::

        Slot 1:
        PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
        1       Normal   AC     --          --          --        Back-to-front
        2       Absent   AC     --          --          --        Back-to-front

        Slot 2:
        PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
        1       Normal   AC     1.2         12.0        150       Back-to-front

    Also handles ``PS slot/id`` format::

        Power Supply Status:
        PS 1/1         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 180W
        PS 1/2         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 175W

    Notes:
        - ps_id formatted as ``PS {slot}/{power_id}`` (e.g. "PS 1/1").
        - State: Normal, Absent, Fail, etc.
        - Power(W) column: ``--`` means not available.
    """

    device_type = DeviceType.HPE
    command = "get_power_hpe_dna"

    # Matches "Slot X:" header line
    SLOT_PATTERN = re.compile(r"^\s*Slot\s+(\d+)\s*:", re.MULTILINE)

    # Matches data rows in the display-power table format
    # PowerID  State  Mode  Current(A)  Voltage(V)  Power(W)  FanDirection
    DATA_ROW_PATTERN = re.compile(
        r"^\s*(?P<power_id>\d+)\s+"
        r"(?P<state>\S+)\s+"
        r"(?P<mode>\S+)\s+"
        r"(?P<current>\S+)\s+"
        r"(?P<voltage>\S+)\s+"
        r"(?P<power>\S+)"
        r"(?:\s+(?P<fan_dir>\S+))?\s*$",
        re.MULTILINE,
    )

    # Matches the alternative "PS slot/id  Status  Input: ...  Output: ...  Capacity: ...  Actual: ..." format
    PS_LINE_PATTERN = re.compile(
        r"^\s*PS\s+(?P<ps_id>\S+)\s+"
        r"(?P<status>\S+)"
        r"(?:\s+Input:\s*(?P<input>\S+))?"
        r"(?:\s+Output:\s*(?P<output>\S+))?"
        r"(?:\s+Capacity:\s*(?P<capacity>\d+(?:\.\d+)?)\s*W?)?"
        r"(?:\s+Actual:\s*(?P<actual>\d+(?:\.\d+)?)\s*W?)?\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    def parse(self, raw_output: str) -> list[PowerData]:
        results: list[PowerData] = []

        # First, try the alternative "PS slot/id" format
        ps_matches = list(self.PS_LINE_PATTERN.finditer(raw_output))
        if ps_matches:
            for match in ps_matches:
                ps_id = match.group("ps_id")
                status = match.group("status")

                results.append(PowerData(
                    ps_id=f"PS {ps_id}",
                    status=status,
                ))
            return results

        # Primary format: display power with Slot headers and data rows
        # Build a mapping of line positions to slot numbers
        slot_positions: list[tuple[int, str]] = []
        for slot_match in self.SLOT_PATTERN.finditer(raw_output):
            slot_positions.append((slot_match.start(), slot_match.group(1)))

        for match in self.DATA_ROW_PATTERN.finditer(raw_output):
            power_id = match.group("power_id")
            state = match.group("state")

            # Determine which slot this row belongs to
            row_pos = match.start()
            current_slot = "1"  # default if no Slot header found
            for slot_pos, slot_num in slot_positions:
                if slot_pos < row_pos:
                    current_slot = slot_num
                else:
                    break

            # Format ps_id as "PS {slot}/{power_id}"
            ps_id = f"PS {current_slot}/{power_id}"

            results.append(PowerData(
                ps_id=ps_id,
                status=state,
            ))

        return results


# Register parser
parser_registry.register(GetPowerHpeDnaParser())
