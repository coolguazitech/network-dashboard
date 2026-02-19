"""
Parser for 'get_error_count_hpe_fna' API.

Parses HPE Comware ``display counters inbound interface`` and
``display counters outbound interface`` output to extract per-interface
error counters.

=== ParsedData Model (DO NOT REMOVE) ===
class InterfaceErrorData(ParsedData):
    interface_name: str                      # e.g. "Gi1/0/1", "GE1/0/1"
    crc_errors: int = 0                      # CRC error count only, >= 0
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display counters inbound interface / display counters outbound interface
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class GetErrorCountHpeFnaParser(BaseParser[InterfaceErrorData]):
    """
    Parser for HPE Comware error counter output.

    Handles three formats:

    Format A — ``display counters inbound interface`` (real CLI)::

        Interface             Total(pkts)  Broadcast   Multicast  Err(pkts)
        GE1/0/1                    123456       1234         567          0
        GE1/0/2                     98765        876         432          5
        XGE1/0/25                  654321       5432        1234          0

    ``display counters outbound interface``::

        Interface             Total(pkts)  Broadcast   Multicast  Err(pkts)
        GE1/0/1                    234567       2345         678          0
        GE1/0/2                    187654       1876         543          1

    Format B — ``display interface`` per-interface blocks
    (ref: NTC-templates ``hp_comware_display_interface.raw``)::

        GigabitEthernet1/0/1
        Current state: UP
        ...
        Input:  0 input errors, 0 runts, 0 giants, 0 throttles
                0 CRC, 0 frame, 0 overruns, 0 aborts
        ...
        Output: 0 output errors, 0 underruns, 0 buffer failures

    Format C — simplified FNA tabular format::

        Interface            Input(errs)       Output(errs)
        GE1/0/1                        0                  0
        GE1/0/2                        5                  1

    Parsing rules:
    - Format A/C: ``crc_errors`` = sum of all error columns.
    - Format B: ``crc_errors`` = input_errors + output_errors per interface.
    """

    device_type = DeviceType.HPE
    command = "get_error_count_hpe_fna"

    # Per-interface block header: interface name on its own line
    # HPE Comware uses bare interface name, not "IntfName is up/down"
    _INTF_LINE_PATTERN = re.compile(
        r"^((?:GigabitEthernet|Ten-GigabitEthernet|HundredGigE|FortyGigE|"
        r"Twenty-FiveGigE|Bridge-Aggregation|XGE|GE|BAGG|Vlan-interface)"
        r"\S*)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # "N input errors" line in display interface
    _INPUT_ERRORS_PATTERN = re.compile(
        r"(\d+)\s+input\s+errors?", re.IGNORECASE
    )

    # "N output errors" line in display interface
    _OUTPUT_ERRORS_PATTERN = re.compile(
        r"(\d+)\s+output\s+errors?", re.IGNORECASE
    )

    # Tabular data row: interface name, then one or more integer columns.
    _MULTI_COL_PATTERN = re.compile(
        r"^\s*(?P<intf>\S+)"
        r"(?P<nums>(?:\s+\d+)+)"
        r"\s*$",
        re.MULTILINE,
    )

    # Header detection (skip header lines).
    _HEADER_PATTERN = re.compile(r"Interface\b", re.IGNORECASE)

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        if not raw_output or not raw_output.strip():
            return []

        # Detect per-interface block format
        if (self._INPUT_ERRORS_PATTERN.search(raw_output)
                and self._INTF_LINE_PATTERN.search(raw_output)):
            return self._parse_per_interface(raw_output)

        # Otherwise, parse as tabular
        return self._parse_tabular(raw_output)

    def _parse_per_interface(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse ``display interface`` per-interface error blocks."""
        results: list[InterfaceErrorData] = []

        intf_matches = list(self._INTF_LINE_PATTERN.finditer(raw_output))

        for i, match in enumerate(intf_matches):
            intf_name = match.group(1)
            start = match.start()
            end = (intf_matches[i + 1].start()
                   if i + 1 < len(intf_matches) else len(raw_output))
            block = raw_output[start:end]

            total_errors = 0

            input_match = self._INPUT_ERRORS_PATTERN.search(block)
            if input_match:
                total_errors += int(input_match.group(1))

            output_match = self._OUTPUT_ERRORS_PATTERN.search(block)
            if output_match:
                total_errors += int(output_match.group(1))

            results.append(
                InterfaceErrorData(
                    interface_name=intf_name,
                    crc_errors=total_errors,
                )
            )

        return results

    def _parse_tabular(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse simplified tabular format."""
        results: list[InterfaceErrorData] = []

        for line in raw_output.splitlines():
            stripped = line.strip()

            if not stripped:
                continue
            if self._HEADER_PATTERN.search(stripped):
                continue
            if stripped.startswith("-"):
                continue

            match = self._MULTI_COL_PATTERN.match(line)
            if not match:
                continue

            interface_name = match.group("intf")
            nums_str = match.group("nums").strip()
            error_values = [int(n) for n in nums_str.split()]
            crc_errors = sum(error_values)

            results.append(
                InterfaceErrorData(
                    interface_name=interface_name,
                    crc_errors=crc_errors,
                )
            )

        return results


# Register parser
parser_registry.register(GetErrorCountHpeFnaParser())
