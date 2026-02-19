"""
Parser for 'get_error_count_nxos_fna' API.

Parses Cisco NX-OS ``show interface counters errors`` multi-section tabular
output to extract per-interface error counters.

=== ParsedData Model (DO NOT REMOVE) ===
class InterfaceErrorData(ParsedData):
    interface_name: str                      # e.g. "Gi1/0/1", "GE1/0/1"
    crc_errors: int = 0                      # CRC error count only, >= 0
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show interface counters errors
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class GetErrorCountNxosFnaParser(BaseParser[InterfaceErrorData]):
    """
    Parser for Cisco NX-OS ``show interface counters errors`` output.

    Real CLI output has **multiple sections** with different error categories.
    The same port appears in each section (ref: Cisco NX-OS CLI docs)::

        --------------------------------------------------------------------------------
        Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        --------------------------------------------------------------------------------
        Eth1/1                0          0          0          0          0           0
        Eth1/2                0          3          2          5          0           0

        --------------------------------------------------------------------------------
        Port          Single-Col  Multi-Col  Late-Col  InDiscards
        --------------------------------------------------------------------------------
        Eth1/1                 0          0         0           0
        Eth1/2                 0          0         0           0

        --------------------------------------------------------------------------------
        Port          Giants SQETest-Err Deferred-Tx IntMacTx-Er IntMacRx-Er
        --------------------------------------------------------------------------------
        Eth1/1             0           0           0           0           0

        --------------------------------------------------------------------------------
        Port          Stomped-CRC
        --------------------------------------------------------------------------------
        Eth1/1                  0

    Also handles ``show interface`` per-interface blocks (ref: NTC-templates)::

        Ethernet1/1 is up
          ...
          0 runts  0 giants  0 CRC  0 no buffer
          0 input error  0 short frame  0 overrun   0 underrun  0 ignored
          0 output error  0 collision  0 deferred  0 late collision

    Parsing rules:
    - Errors from the same port across **multiple sections are summed**.
    - ``crc_errors`` = sum of all error columns across all sections.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_error_count_nxos_fna"

    # Separator line: only dashes and whitespace.
    _SEPARATOR_PATTERN = re.compile(r"^[\s\-]+$")

    # Header detection.
    _HEADER_PATTERN = re.compile(r"Port\b", re.IGNORECASE)

    # Data row: interface name followed by one or more integer columns.
    _ROW_PATTERN = re.compile(
        r"^\s*(?P<intf>\S+)"
        r"(?P<nums>(?:\s+\d+)+)"
        r"\s*$",
        re.MULTILINE,
    )

    # Per-interface block: "InterfaceName is up/down"
    _INTF_HEADER_PATTERN = re.compile(
        r"^(\S+)\s+is\s+(?:up|down|administratively)", re.MULTILINE | re.IGNORECASE
    )

    # NX-OS per-interface: "N input error"
    _INPUT_ERRORS_PATTERN = re.compile(r"(\d+)\s+input\s+errors?", re.IGNORECASE)

    # NX-OS per-interface: "N output error"
    _OUTPUT_ERRORS_PATTERN = re.compile(r"(\d+)\s+output\s+errors?", re.IGNORECASE)

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        if not raw_output or not raw_output.strip():
            return []

        # Detect per-interface block format
        if self._INTF_HEADER_PATTERN.search(raw_output):
            return self._parse_per_interface(raw_output)

        return self._parse_tabular(raw_output)

    def _parse_tabular(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse multi-section tabular format, aggregating errors per port."""
        error_totals: dict[str, int] = {}
        order: list[str] = []

        for line in raw_output.splitlines():
            stripped = line.strip()

            if not stripped:
                continue
            if self._SEPARATOR_PATTERN.match(stripped):
                continue
            if self._HEADER_PATTERN.search(stripped):
                continue

            match = self._ROW_PATTERN.match(line)
            if not match:
                continue

            interface_name = match.group("intf")
            nums_str = match.group("nums").strip()
            error_values = [int(n) for n in nums_str.split()]
            section_errors = sum(error_values)

            # Aggregate across sections
            if interface_name not in error_totals:
                order.append(interface_name)
                error_totals[interface_name] = 0
            error_totals[interface_name] += section_errors

        return [
            InterfaceErrorData(
                interface_name=intf,
                crc_errors=error_totals[intf],
            )
            for intf in order
        ]

    def _parse_per_interface(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse ``show interface`` per-interface error blocks."""
        results: list[InterfaceErrorData] = []

        intf_matches = list(self._INTF_HEADER_PATTERN.finditer(raw_output))

        for i, match in enumerate(intf_matches):
            intf_name = match.group(1)
            start = match.start()
            end = intf_matches[i + 1].start() if i + 1 < len(intf_matches) else len(raw_output)
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


# Register parser
parser_registry.register(GetErrorCountNxosFnaParser())
