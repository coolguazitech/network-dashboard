"""
Parser for 'get_version_hpe_dna' API.

Parses HPE Comware `display version` output to extract firmware version.

Real CLI command: display version
Platforms: HPE Comware (5710, 5940, 5945, 5130, etc.)

=== ParsedData Model (DO NOT REMOVE) ===
class VersionData(ParsedData):
    version: str                             # firmware version string
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display version
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class GetVersionHpeDnaParser(BaseParser[VersionData]):
    """
    Parser for HPE Comware ``display version`` output.

    Real CLI output (ref: HPE Comware CLI Reference)::

        HPE Comware Platform Software
        Comware Software, Version 7.1.070, Release 6635P07
        Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
        HPE FF 5710 48SFP+ 6QS 2SL Switch
        Uptime is 0 weeks, 1 day, 3 hours, 22 minutes
        ...

    ArubaOS-CX variant::

        Software Version: WC.16.11.0012
        Model: Aruba 6300M
        Serial Number: SG12345678
        Uptime: 45 days, 3 hours

    Notes:
        - Version: ``Version X, Release Y`` or ``Software Version: X``
    """

    device_type = DeviceType.HPE
    command = "get_version_hpe_dna"

    # Version patterns
    # "Comware Software, Version 7.1.070, Release 6635P07"
    COMWARE_VERSION_RELEASE_PATTERN = re.compile(
        r"Version\s+(?P<version>\S+),\s*Release\s+(?P<release>\S+)",
        re.IGNORECASE,
    )
    # "Version 7.1.070" (without Release)
    COMWARE_VERSION_PATTERN = re.compile(
        r"Version\s+(?P<version>\S+)",
        re.IGNORECASE,
    )
    # "Software Version: WC.16.11.0012"
    SOFTWARE_VERSION_PATTERN = re.compile(
        r"Software\s+Version:\s*(?P<version>\S+)",
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
        """Extract version string from output."""
        # Try "Software Version: X" first (key-value format)
        match = self.SOFTWARE_VERSION_PATTERN.search(output)
        if match:
            return match.group("version")

        # Try "Version X, Release Y" format (most specific)
        match = self.COMWARE_VERSION_RELEASE_PATTERN.search(output)
        if match:
            version = match.group("version")
            release = match.group("release")
            return f"{version} Release {release}"

        # Try plain "Version X" format
        match = self.COMWARE_VERSION_PATTERN.search(output)
        if match:
            version = match.group("version").rstrip(",")
            return version

        return None


# Register parser
parser_registry.register(GetVersionHpeDnaParser())
