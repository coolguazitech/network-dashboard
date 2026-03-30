"""
Parser for 'get_version_nxos_fna' API.

Parses Cisco NX-OS ``show install active`` output to extract installed packages.

Real CLI command: show install active
Platforms: Nexus 9000, 7000, 5000 series

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


class GetVersionNxosFnaParser(BaseParser[VersionData]):
    """
    Parser for Cisco NX-OS ``show install active`` output.

    Real CLI output example::

        Boot Image:
                NXOS Image: bootflash:///nxos64-cs.10.3.3.F.bin

        Active Packages:
                bootflash:///nxos.CSCab12345-n9k_ALL-1.0.0-10.3.3.F.lib32_64_n9000

    Extracts lines containing ``bootflash:`` paths.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_version_nxos_fna"

    # Match bootflash: paths (with optional /// prefix)
    BOOTFLASH_PATTERN = re.compile(
        r"(bootflash:/{0,3}\S+)", re.MULTILINE,
    )

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
parser_registry.register(GetVersionNxosFnaParser())
