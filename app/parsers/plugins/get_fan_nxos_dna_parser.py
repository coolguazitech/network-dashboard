"""
Parser for 'get_fan_nxos_dna' API.

Parses Cisco NXOS ``show environment fan`` table output to extract fan status.

=== ParsedData Model (DO NOT REMOVE) ===
class FanStatusData(ParsedData):
    fan_id: str                              # e.g. "Fan 1/1", "FAN 1", "Fan1(sys_fan1)"
    status: str                              # auto-normalized → OperationalStatus

Valid status values: ok, good, normal, online, active, fail, absent, unknown
Status is auto-normalized (case-insensitive): "Normal"→"normal", "OK"→"ok", "Absent"→"absent"
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show environment fan
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class GetFanNxosDnaParser(BaseParser[FanStatusData]):
    """
    Parser for Cisco NX-OS ``show environment fan`` tabular output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_environment.raw``,
    fan section from ``show environment``)::

        Fan:
        --------------------------------------------------------------------------
        Fan             Model                Hw     Direction      Status
        --------------------------------------------------------------------------
        Fan1(sys_fan1)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan2(sys_fan2)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan3(sys_fan3)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan_in_PS1      --                   --     front-to-back  Ok
        Fan_in_PS2      --                   --     front-to-back  Absent

    Notes:
        - Fan ID is the first column (e.g. ``Fan1(sys_fan1)``, ``Fan_in_PS1``).
        - Status is the last column (Ok, Absent, Fail, etc.).
        - The ``Direction`` column may or may not be present depending on platform.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_fan_nxos_dna"

    # Header keywords (case-insensitive first token)
    HEADER_KEYWORDS = {"fan", "---", "==="}

    # Data row pattern: first column (fan id), middle columns, last column (status)
    # We use a flexible pattern that captures the first non-whitespace token
    # and the last non-whitespace token on lines with at least 2 columns.
    ROW_PATTERN = re.compile(
        r"^(\S+)\s+(.+?)\s+(\S+)\s*$", re.MULTILINE
    )

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results: list[FanStatusData] = []

        if not raw_output or not raw_output.strip():
            return results

        header_skipped = False

        for line in raw_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # Skip separator lines (e.g., "------...")
            if re.match(r"^[-=]+$", stripped):
                header_skipped = True
                continue

            # Skip the header line (first non-empty, non-separator line
            # that starts with a header keyword)
            if not header_skipped:
                first_token = stripped.split()[0].lower()
                # If the first token matches a known header keyword
                # (e.g., "Fan" when followed by "Model"), skip it
                if first_token in self.HEADER_KEYWORDS or "model" in stripped.lower():
                    continue

            # Parse data rows
            row_match = self.ROW_PATTERN.match(stripped)
            if not row_match:
                continue

            fan_id = row_match.group(1)
            status = row_match.group(3)

            # Extra safety: skip if fan_id looks like a header
            if fan_id.lower() == "fan" and "model" in row_match.group(2).lower():
                continue

            results.append(
                FanStatusData(
                    fan_id=fan_id,
                    status=status,
                )
            )

        return results


# Register parser
parser_registry.register(GetFanNxosDnaParser())
