"""Parser for 'get_error_count_ios_fna' API."""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class GetErrorCountIosFnaParser(BaseParser[InterfaceErrorData]):
    """
    Parser for Cisco IOS error counter output.

    Handles three formats:

    Format A — ``show interfaces counters errors`` (real CLI, ref: NTC-templates)::

        Port        Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        Gi0/1               0          0          0          0          0           0
        Gi0/2               0          5          0          3          0           0

    Format B — ``show interfaces`` per-interface blocks (real CLI)::

        GigabitEthernet0/1 is up, line protocol is up
          ...
             0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
          ...
             0 output errors, 0 collisions, 2 interface resets

    Format C — simplified FNA format (if API pre-processes output)::

        Interface            Input(errs)       Output(errs)
        Gi1/0/1                        0                  0

    Parsing rules:
    - Format A/C: ``crc_errors`` = sum of all numeric error columns.
    - Format B: ``crc_errors`` = input_errors + output_errors per interface.
    - Header and separator lines are skipped.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_error_count_ios_fna"

    # Tabular format: interface name followed by one or more integer columns.
    _MULTI_COL_PATTERN = re.compile(
        r"^\s*(?P<intf>\S+)"
        r"(?P<nums>(?:\s+\d+)+)"
        r"\s*$",
        re.MULTILINE,
    )

    # Per-interface block: "InterfaceName is up/down"
    _INTF_HEADER_PATTERN = re.compile(
        r"^(\S+)\s+is\s+(?:up|down|administratively)", re.MULTILINE | re.IGNORECASE
    )

    # Per-interface error line: "N input errors, N CRC, ..."
    _INPUT_ERRORS_PATTERN = re.compile(
        r"(\d+)\s+input\s+errors?", re.IGNORECASE
    )

    # Per-interface output error line: "N output errors"
    _OUTPUT_ERRORS_PATTERN = re.compile(
        r"(\d+)\s+output\s+errors?", re.IGNORECASE
    )

    # Header detection (skip header lines).
    _HEADER_PATTERN = re.compile(r"Port\b|Interface\b", re.IGNORECASE)

    # Separator line: only dashes and whitespace.
    _SEPARATOR_PATTERN = re.compile(r"^[\s\-]+$")

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        if not raw_output or not raw_output.strip():
            return []

        # Detect format: per-interface blocks have "is up/down" lines
        if self._INTF_HEADER_PATTERN.search(raw_output):
            return self._parse_per_interface(raw_output)

        # Otherwise, parse as tabular (multi-column or simplified)
        return self._parse_tabular(raw_output)

    def _parse_tabular(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse tabular format (multi-column counters or simplified)."""
        results: list[InterfaceErrorData] = []

        for line in raw_output.splitlines():
            stripped = line.strip()

            if not stripped:
                continue
            if self._HEADER_PATTERN.search(stripped):
                continue
            if self._SEPARATOR_PATTERN.match(stripped):
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

    def _parse_per_interface(self, raw_output: str) -> list[InterfaceErrorData]:
        """Parse ``show interfaces`` per-interface error blocks."""
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
parser_registry.register(GetErrorCountIosFnaParser())
