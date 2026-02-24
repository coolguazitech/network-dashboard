"""
Parser for 'get_version_ios_dna' API.

Parses Cisco IOS/IOS-XE `show version` output to extract firmware version.

Real CLI command: show version
Platforms: Catalyst 2960, 3560, 3750, 3850, 9200, 9300, 9500

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


class GetVersionIosDnaParser(BaseParser[VersionData]):
    """
    Parser for Cisco IOS/IOS-XE ``show version`` output.

    Real CLI output (ref: NTC-templates ``cisco_ios_show_version.raw``)::

        Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10
        Technical Support: http://www.cisco.com/techsupport
        Copyright (c) 1986-2020 by Cisco Systems, Inc.
        ...
        ROM: Bootstrap program is C3750E boot loader
        BOOTLDR: C3750E Boot Loader Version 12.2(58r)SE
        SW-ACCESS-01 uptime is 30 weeks, 2 days, 14 hours, 5 minutes
        ...
        Model number          : WS-C3750X-48PF-L
        System serial number  : FDO1234A5BC
        ...

    IOS-XE variant::

        Cisco IOS XE Software, Version 17.09.04a
        Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4a
        ...
        cisco C9300-48P (X86) processor with 1419044K/6147K bytes of memory.
        Processor board ID FJC2345G0CD
        ...

    Notes:
    - Version: ``Version X.Y.Z`` or ``Version X.Y(Z)A``
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_version_ios_dna"

    # Version patterns
    # "Cisco IOS Software, Version 17.9.4" or "Version 15.2(7)E4"
    VERSION_PATTERN = re.compile(
        r"Version\s+(?P<version>\S+)",
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
        match = self.VERSION_PATTERN.search(output)
        if match:
            version = match.group("version")
            # Strip trailing comma if present
            return version.rstrip(",")
        return None


# Register parser
parser_registry.register(GetVersionIosDnaParser())
