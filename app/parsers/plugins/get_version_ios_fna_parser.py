"""
Parser for 'get_version_ios_fna' API.

Parses Cisco IOS/IOS-XE ``show install active`` output to extract installed packages.

Real CLI command: show install active
Platforms: Catalyst 9200, 9300, 9500, 3850, etc.

=== ParsedData Model (DO NOT REMOVE) ===
class VersionData(ParsedData):
    packages: list[str]                  # installed package list
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show install active
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class GetVersionIosFnaParser(BaseParser[VersionData]):
    """
    Parser for Cisco IOS/IOS-XE ``show install active`` output.

    Real CLI output example (IOS-XE 17.x)::

        Package: Provisioning File, version: 17.09.04a, status: active
          File: bootflash:packages.conf, on: RP0
        Package: rpbase, version: 17.09.04a, status: active
          File: bootflash:cat9k-rpbase.17.09.04a.SPA.pkg, on: RP0

    Older format::

        Active Packages:
            bootflash:cat9k_iosxe.17.09.04a.SPA.bin

    Extracts lines containing ``bootflash:`` paths.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_version_ios_fna"

    # Match bootflash: paths anywhere in text (FNA may return single-line)
    BOOTFLASH_PATTERN = re.compile(r"bootflash:/{0,3}\S+")

    def parse(self, raw_output: str) -> list[VersionData]:
        if not raw_output or not raw_output.strip():
            return []

        packages = self.BOOTFLASH_PATTERN.findall(raw_output)
        if not packages:
            return []

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for pkg in packages:
            if pkg not in seen:
                seen.add(pkg)
                unique.append(pkg)

        return [VersionData(packages=unique)]


# Register parser
parser_registry.register(GetVersionIosFnaParser())
