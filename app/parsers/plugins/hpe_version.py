"""
HPE Comware Version Parser.
"""
from __future__ import annotations

import re

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class HpeVersionParser(BaseParser[VersionData]):
    """Parser for HPE Comware version information."""

    vendor = VendorType.HPE
    platform = PlatformType.HPE_COMWARE
    indicator_type = "version"
    command = "display version"

    def parse(self, raw_output: str) -> list[VersionData]:
        """
        Parse 'display version' output.

        Example:
        HPE Comware Platform Software
        Comware Software, Version 7.1.070, Release 6635P07
        Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
        HPE FF 5710 48SFP+ 6QS 2SL Switch
        """
        version = None
        model = None

        for line in raw_output.strip().splitlines():
            line = line.strip()

            # Match Release version: "Release 6635P07"
            release_match = re.search(r"Release\s+(\S+)", line)
            if release_match:
                version = release_match.group(1)
                continue

            # Match model line: "HPE FF 5710 ..."
            if line.startswith("HPE") and "Switch" in line:
                model = line
                continue

        if not version:
            # Fallback: try Comware Software Version
            for line in raw_output.strip().splitlines():
                ver_match = re.search(
                    r"Version\s+([\d.]+)", line
                )
                if ver_match:
                    version = ver_match.group(1)
                    break

        if version:
            return [
                VersionData(
                    version=version,
                    model=model,
                )
            ]

        return []


# Register parser
parser_registry.register(HpeVersionParser())
