"""
Parser for 'get_version_nxos_dna' API.

Parses Cisco NXOS `show version` output to extract firmware version,
model, serial number, and uptime information.

Real CLI command: show version
Platforms: Nexus 9000, 7000, 5000 series
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
    - Model: ``cisco NexusXXXX CYYYYY Chassis`` under Hardware section
    - Serial: ``Processor Board ID X``
    - Uptime: ``Kernel uptime is X`` (NX-OS native) or ``Uptime is X``
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

    # Model patterns
    # "cisco Nexus9000 C9336C-FX2 Chassis" or "cisco Nexus9000 C93180YC-FX"
    # Must contain a product code (like C9336C-FX2), NOT "Operating System" or "Software"
    MODEL_PATTERN = re.compile(
        r"^\s*cisco\s+(?P<model>Nexus\d+\S*\s+\S+.*?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    # Broader fallback: any line with "Chassis" under Hardware
    CHASSIS_PATTERN = re.compile(
        r"^\s*(?P<model>\S+.*?Chassis.*?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Serial number pattern
    # "Processor Board ID SAL2345ABCD"
    PROCESSOR_ID_PATTERN = re.compile(
        r"Processor\s+Board\s+ID\s+(?P<serial>\S+)",
        re.IGNORECASE,
    )

    # Uptime patterns
    # "Kernel uptime is 60 day(s), 5 hour(s), 30 minute(s)"
    KERNEL_UPTIME_PATTERN = re.compile(
        r"Kernel\s+uptime\s+is\s+(?P<uptime>.+?)(?:\s*$)",
        re.MULTILINE | re.IGNORECASE,
    )
    # "Uptime is 0 weeks, 1 day, 3 hours"
    UPTIME_PATTERN = re.compile(
        r"(?<!\w)[Uu]ptime\s+is\s+(?P<uptime>.+?)(?:\s*$)",
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

    def _extract_model(self, output: str) -> str | None:
        """Extract model/chassis string from output."""
        # Try "cisco Nexus..." line first
        match = self.MODEL_PATTERN.search(output)
        if match:
            model = match.group("model").strip()
            # Clean up trailing Chassis/etc. text but keep it informative
            return model

        # Fallback to line with "Chassis"
        match = self.CHASSIS_PATTERN.search(output)
        if match:
            model = match.group("model").strip()
            # Filter out false positives
            if "copyright" in model.lower() or "http" in model.lower():
                return None
            return model

        return None

    def _extract_serial(self, output: str) -> str | None:
        """Extract serial number from output."""
        match = self.PROCESSOR_ID_PATTERN.search(output)
        if match:
            return match.group("serial")
        return None

    def _extract_uptime(self, output: str) -> str | None:
        """Extract uptime string from output."""
        # Try "Kernel uptime is X" first (more specific)
        match = self.KERNEL_UPTIME_PATTERN.search(output)
        if match:
            return match.group("uptime").strip()

        # Fall back to generic "Uptime is X"
        match = self.UPTIME_PATTERN.search(output)
        if match:
            return match.group("uptime").strip()

        return None


# Register parser
parser_registry.register(GetVersionNxosDnaParser())
