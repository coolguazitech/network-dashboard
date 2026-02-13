"""
Parser for 'get_power_nxos_dna' API.

Parses Cisco NXOS `show environment power` tabular output to extract
power supply status, capacity, and actual output wattage.

Real CLI command: show environment power
Platforms: Nexus 9000, 7000, 5000 series
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class GetPowerNxosDnaParser(BaseParser[PowerData]):
    """
    Parser for Cisco NX-OS ``show environment power`` output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_environment.raw``,
    power section from ``show environment``)::

        Power Supply:
        Voltage: 12 Volts
        Power                              Actual        Total
        Supply    Model                    Output     Capacity    Status
        -------  -------------------  -----------  -----------  ----------
        1        NXA-PAC-1100W-PE          186 W      1100 W     Ok
        2        NXA-PAC-1100W-PE            0 W      1100 W     Absent

                                         Actual        Power
        Module    Model                  Draw       Allocated    Status
        -------  -------------------  -----------  -----------  ----------
        1        N9K-C93180YC-FX       117.84 W    252.00 W     Powered-Up

    Notes:
        - Supply ID is numeric (1, 2, ...) or ``PS-N`` format.
        - Actual Output/Draw may include ``W`` suffix.
        - Status: Ok, Absent, Shutdown, Failed, etc.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_power_nxos_dna"

    # Data row for the standard Nexus format:
    # ID   Model                Actual_Output   Total_Capacity   Status
    STANDARD_ROW_PATTERN = re.compile(
        r"^\s*(?P<id>\d+)\s+"
        r"(?P<model>\S+)\s+"
        r"(?P<actual>\d+(?:\.\d+)?)\s+"
        r"(?P<capacity>\d+(?:\.\d+)?)\s+"
        r"(?P<status>\S+)\s*$",
        re.MULTILINE,
    )

    # Data row for the "PS-N" format:
    # PS-N   Model   Actual_Output [W]   Status
    PS_ROW_PATTERN = re.compile(
        r"^\s*(?P<ps_id>PS-?\d+)\s+"
        r"(?P<model>\S+)\s+"
        r"(?P<actual>\d+(?:\.\d+)?)\s*W?\s+"
        r"(?P<status>\S+)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # More flexible row: catches lines with "W" unit in Actual Output column
    # e.g. "1   NXA-PAC-1100W-PE   186 W   1100 W   Ok"
    FLEXIBLE_ROW_PATTERN = re.compile(
        r"^\s*(?P<id>\d+)\s+"
        r"(?P<model>\S+)\s+"
        r"(?P<actual>\d+(?:\.\d+)?)\s*W?\s+"
        r"(?P<capacity>\d+(?:\.\d+)?)\s*W?\s+"
        r"(?P<status>\S+)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    @staticmethod
    def _parse_watts(value: str | None) -> float | None:
        """Parse a wattage value, stripping 'W' suffix."""
        if value is None:
            return None
        value = value.strip().rstrip("Ww").strip()
        if value in ("--", "N/A", "n/a", ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def parse(self, raw_output: str) -> list[PowerData]:
        results: list[PowerData] = []
        seen_ids: set[str] = set()

        # Try standard numeric ID format first
        for match in self.STANDARD_ROW_PATTERN.finditer(raw_output):
            ps_num = match.group("id")
            ps_id = f"PS-{ps_num}"
            actual = self._parse_watts(match.group("actual"))
            capacity = self._parse_watts(match.group("capacity"))
            status = match.group("status")

            if ps_id not in seen_ids:
                seen_ids.add(ps_id)
                results.append(PowerData(
                    ps_id=ps_id,
                    status=status,
                    capacity_watts=capacity,
                    actual_output_watts=actual,
                ))

        # Try "PS-N" format
        for match in self.PS_ROW_PATTERN.finditer(raw_output):
            ps_id = match.group("ps_id").upper()
            # Normalize to "PS-N" format
            if not ps_id.startswith("PS-"):
                ps_id = ps_id.replace("PS", "PS-")
            actual = self._parse_watts(match.group("actual"))
            status = match.group("status")

            if ps_id not in seen_ids:
                seen_ids.add(ps_id)
                results.append(PowerData(
                    ps_id=ps_id,
                    status=status,
                    actual_output_watts=actual,
                ))

        # Fallback: flexible format with "W" unit markers
        if not results:
            for match in self.FLEXIBLE_ROW_PATTERN.finditer(raw_output):
                ps_num = match.group("id")
                ps_id = f"PS-{ps_num}"
                actual = self._parse_watts(match.group("actual"))
                capacity = self._parse_watts(match.group("capacity"))
                status = match.group("status")

                if ps_id not in seen_ids:
                    seen_ids.add(ps_id)
                    results.append(PowerData(
                        ps_id=ps_id,
                        status=status,
                        capacity_watts=capacity,
                        actual_output_watts=actual,
                    ))

        return results


# Register parser
parser_registry.register(GetPowerNxosDnaParser())
