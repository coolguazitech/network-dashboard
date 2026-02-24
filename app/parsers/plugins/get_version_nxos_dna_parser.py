"""
Parser for 'get_version_nxos_dna' API.

Parses Cisco NXOS `show version` output to extract firmware version.

Real CLI command: show version
Platforms: Nexus 9000, 7000, 5000 series

=== ParsedData Model (DO NOT REMOVE) ===
class VersionData(ParsedData):
    version: str                             # firmware version string
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show version
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class GetVersionNxosDnaParser(BaseParser[VersionData]):
    """
    Parser for Cisco NX-OS ``show version`` output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_version.raw``)::

        Cisco Nexus Operating System (NX-OS) Software
        TAC support: http://www.cisco.com/tac
        Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html
        Copyright (c) 2002-2022, Cisco Systems, Inc. All rights reserved.
        ...
          NXOS: version 9.3(8)
        ...
        Hardware
          cisco Nexus9000 C93180YC-FX Chassis
          Intel(R) Xeon(R) CPU D-1528 @ 1.90GHz with 24576712 kB of memory.
          Processor Board ID FDO21510JKR
        ...
        Kernel uptime is 60 day(s), 5 hour(s), 30 minute(s), 22 second(s)

    Notes:
    - Version: ``NXOS: version X.Y(Z)`` or ``NXOS: version X.Y.Z``
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_version_nxos_dna"

    # Version patterns
    # "NXOS: version 10.3.3" or "NXOS: version 9.3(8)"
    NXOS_VERSION_PATTERN = re.compile(
        r"NXOS:\s*version\s+(?P<version>\S+)",
        re.IGNORECASE,
    )
    # Fallback: "system:    version X" or "kickstart: version X"
    SYSTEM_VERSION_PATTERN = re.compile(
        r"(?:system|NXOS|Software)\s*:\s*version\s+(?P<version>\S+)",
        re.IGNORECASE,
    )

    def parse(self, raw_output: str) -> list[VersionData]:
        if not raw_output or not raw_output.strip():
            return []

        version = self._extract_version(raw_output)
        if not version:
            return []

        return [VersionData(
            version=version,
        )]

    def _extract_version(self, output: str) -> str | None:
        """Extract NXOS version string from output."""
        # Try "NXOS: version X" first
        match = self.NXOS_VERSION_PATTERN.search(output)
        if match:
            return match.group("version")

        # Fallback to broader pattern
        match = self.SYSTEM_VERSION_PATTERN.search(output)
        if match:
            return match.group("version")

        return None


# Register parser
parser_registry.register(GetVersionNxosDnaParser())
