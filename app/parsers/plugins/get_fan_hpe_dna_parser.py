"""
Parser for 'get_fan_hpe_dna' API.

Parses HPE Comware ``display fan`` output to extract fan status information
per slot and fan ID.

=== ParsedData Model (DO NOT REMOVE) ===
class FanStatusData(ParsedData):
    fan_id: str                              # e.g. "Fan 1/1", "FAN 1", "Fan1(sys_fan1)"
    status: str                              # auto-normalized → OperationalStatus
    speed_rpm: int | None = None             # optional fan speed in RPM
    speed_percent: int | None = None         # optional fan speed in %

Valid status values: ok, good, normal, online, active, fail, absent, unknown
Status is auto-normalized (case-insensitive): "Normal"→"normal", "OK"→"ok", "Absent"→"absent"
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display fan
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class GetFanHpeDnaParser(BaseParser[FanStatusData]):
    """
    Parser for HPE Comware ``display fan`` output.

    Real CLI output (ref: HPE Comware CLI Reference)::

        Slot 1:
        FanID    Status      Direction
        1        Normal      Back-to-front
        2        Normal      Back-to-front
        3        Absent      Back-to-front
        4        Normal      Back-to-front

        Slot 2:
        FanID    Status      Direction
        1        Normal      Front-to-back
        2        Normal      Front-to-back

    Notes:
        - fan_id formatted as ``Fan {slot}/{fanid}`` (e.g. "Fan 1/1").
        - If no ``Slot X:`` header present, defaults to slot "1".
        - Status: Normal, Absent, Fail, etc.
    """

    device_type = DeviceType.HPE
    command = "get_fan_hpe_dna"

    # Matches "Slot N:" header lines
    SLOT_PATTERN = re.compile(
        r"^Slot\s+(\d+)\s*:", re.MULTILINE | re.IGNORECASE
    )

    # Matches fan data rows: FanID  Status  Direction
    # FanID is a number or alphanumeric identifier; Status is a word;
    # Direction is optional trailing text.
    FAN_ROW_PATTERN = re.compile(
        r"^\s*(\d+)\s+(Normal|Ok|Absent|Fail|Unknown|\S+)\s+(\S.*?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Header keyword to skip
    HEADER_KEYWORDS = {"fanid", "fan_id"}

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results: list[FanStatusData] = []

        if not raw_output or not raw_output.strip():
            return results

        # Split output into slot blocks
        slot_blocks = self._split_by_slot(raw_output)

        for slot, block in slot_blocks:
            self._parse_slot_block(slot, block, results)

        return results

    def _split_by_slot(self, raw_output: str) -> list[tuple[str, str]]:
        """
        Split output into (slot_number, block_text) tuples.

        If no Slot headers are found, treats the entire output as slot "1".
        """
        slot_matches = list(self.SLOT_PATTERN.finditer(raw_output))

        if not slot_matches:
            # No slot headers; treat everything as slot 1
            return [("1", raw_output)]

        blocks: list[tuple[str, str]] = []
        for i, match in enumerate(slot_matches):
            slot_num = match.group(1)
            start = match.end()
            end = (
                slot_matches[i + 1].start()
                if i + 1 < len(slot_matches)
                else len(raw_output)
            )
            blocks.append((slot_num, raw_output[start:end]))

        return blocks

    def _parse_slot_block(
        self,
        slot: str,
        block: str,
        results: list[FanStatusData],
    ) -> None:
        """Parse fan rows within a single slot block."""
        for line in block.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Skip header lines (e.g., "FanID  Status  Direction")
            first_token = line_stripped.split()[0].lower()
            if first_token in self.HEADER_KEYWORDS:
                continue
            if line_stripped.startswith("-"):
                continue

            # Try to match a fan data row
            row_match = self.FAN_ROW_PATTERN.match(line_stripped)
            if not row_match:
                continue

            fan_id_num = row_match.group(1)
            status = row_match.group(2)

            results.append(
                FanStatusData(
                    fan_id=f"Fan {slot}/{fan_id_num}",
                    status=status,
                    speed_rpm=None,
                    speed_percent=None,
                )
            )


# Register parser
parser_registry.register(GetFanHpeDnaParser())
