"""
Parser for 'get_version_ios_dna' API.

Parses Cisco IOS/IOS-XE `show version` output to extract firmware version,
model, serial number, and uptime information.

Real CLI command: show version
Platforms: Catalyst 2960, 3560, 3750, 3850, 9200, 9300, 9500
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
    - Model: ``Model number: X`` or ``cisco Catalyst CXXXX Switch`` line
    - Serial: ``System serial number: X`` or ``Processor board ID X``
    - Uptime: ``hostname uptime is ...`` or ``Uptime is ...``
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_version_ios_dna"

    # Version patterns
    # "Cisco IOS Software, Version 17.9.4" or "Version 15.2(7)E4"
    VERSION_PATTERN = re.compile(
        r"Version\s+(?P<version>\S+)",
        re.IGNORECASE,
    )

    # Model patterns (in priority order)
    # "Model number: WS-C2960X-48FPS-L"
    MODEL_NUMBER_PATTERN = re.compile(
        r"Model\s+number\s*:\s*(?P<model>\S+)",
        re.IGNORECASE,
    )
    # Line containing "Catalyst" or "Switch" that looks like a model line
    # e.g., "Cisco Catalyst C9200L-48P-4G Switch" or "cisco WS-C3750X-48T-L"
    # Must NOT contain "Software", "Copyright", "TAC", etc. (use negative lookahead)
    MODEL_LINE_PATTERN = re.compile(
        r"^\s*[Cc]isco\s+(?P<model>(?!IOS\b)(?!Nexus\b)(?:Catalyst\s+)?\S+.*?(?:Switch|Router|Chassis))\s*$",
        re.MULTILINE,
    )

    # Serial number patterns
    # "System serial number: FCW2345G0AB"
    SYSTEM_SERIAL_PATTERN = re.compile(
        r"System\s+serial\s+number\s*:\s*(?P<serial>\S+)",
        re.IGNORECASE,
    )
    # "Processor board ID FJC2345G0CD"
    PROCESSOR_ID_PATTERN = re.compile(
        r"Processor\s+board\s+ID\s+(?P<serial>\S+)",
        re.IGNORECASE,
    )

    # Uptime patterns
    # "hostname uptime is 30 days, 12 hours, 5 minutes" or "Uptime is ..."
    UPTIME_PATTERN = re.compile(
        r"[Uu]ptime\s+is\s+(?P<uptime>.+?)(?:\s*$)",
        re.MULTILINE,
    )

    def parse(self, raw_output: str) -> list[VersionData]:
        if not raw_output or not raw_output.strip():
            return []

        version = self._extract_version(raw_output)
        if not version:
            return []

        model = self._extract_model(raw_output)
        serial_number = self._extract_serial(raw_output)
        uptime = self._extract_uptime(raw_output)

        return [VersionData(
            version=version,
            model=model,
            serial_number=serial_number,
            uptime=uptime,
        )]

    def _extract_version(self, output: str) -> str | None:
        """Extract version string from output."""
        match = self.VERSION_PATTERN.search(output)
        if match:
            version = match.group("version")
            # Strip trailing comma if present
            return version.rstrip(",")
        return None

    def _extract_model(self, output: str) -> str | None:
        """Extract model string from output."""
        # Try explicit "Model number:" first
        match = self.MODEL_NUMBER_PATTERN.search(output)
        if match:
            return match.group("model").strip()

        # Try line containing Catalyst/Switch with Cisco prefix
        match = self.MODEL_LINE_PATTERN.search(output)
        if match:
            model = match.group("model").strip()
            # Filter out lines that are clearly not model lines
            # (e.g., copyright, TAC support, etc.)
            if any(kw in model.lower() for kw in ("copyright", "tac", "http")):
                return None
            return model

        return None

    def _extract_serial(self, output: str) -> str | None:
        """Extract serial number from output."""
        # Try "System serial number:" first
        match = self.SYSTEM_SERIAL_PATTERN.search(output)
        if match:
            return match.group("serial")

        # Fall back to "Processor board ID"
        match = self.PROCESSOR_ID_PATTERN.search(output)
        if match:
            return match.group("serial")

        return None

    def _extract_uptime(self, output: str) -> str | None:
        """Extract uptime string from output."""
        match = self.UPTIME_PATTERN.search(output)
        if match:
            return match.group("uptime").strip()
        return None


# Register parser
parser_registry.register(GetVersionIosDnaParser())
