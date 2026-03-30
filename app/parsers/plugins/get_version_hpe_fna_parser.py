"""
Parser for 'get_version_hpe_fna' API.

Parses HPE Comware ``show install active`` output to extract installed packages.

Real CLI command: show install active
Platforms: HPE Comware (5710, 5940, 5945, 5130, etc.)

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


class GetVersionHpeFnaParser(BaseParser[VersionData]):
    """
    Parser for HPE Comware ``show install active`` output.

    Real CLI output example::

        Active Packages on slot 1:
          flash:/5710-CMW710-BOOT-R1238P06.bin
          flash:/5710-CMW710-SYSTEM-R1238P06.bin
          flash:/5710-CMW710-PATCH-R1238P06H01.bin
          flash:/5940-CMW710-SECURITY-FIX-01.bin

    The number of ``flash:`` lines varies per device and may include
    boot, system, patch, and additional fix packages.
    """

    device_type = DeviceType.HPE
    command = "get_version_hpe_fna"

    # Lines starting with optional whitespace + "flash:"
    FLASH_PATTERN = re.compile(r"^\s*(flash:/\S+)", re.MULTILINE)

    def parse(self, raw_output: str) -> list[VersionData]:
        if not raw_output or not raw_output.strip():
            return []

        packages = self.FLASH_PATTERN.findall(raw_output)
        if not packages:
            return []

        return [VersionData(packages=packages)]


# Register parser
parser_registry.register(GetVersionHpeFnaParser())
