"""
Parser for 'get_interface_status_hpe_dna' API.

Parses HPE Comware `display interface brief` output to extract
interface link status, speed, and duplex information.

Real CLI command: display interface brief
Platforms: HPE Comware (5710, 5940, 5945, 5130, etc.)

=== ParsedData Model (DO NOT REMOVE) ===
class InterfaceStatusData(ParsedData):
    interface_name: str                      # interface name
    link_status: str                         # normalized to LinkStatus enum
    speed: str | None = None                 # speed string (e.g., "1000M")
    duplex: str | None = None                # normalized to DuplexMode enum
=== End ParsedData Model ===

=== Real CLI Command ===
Command: display interface brief
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceStatusData
from app.parsers.registry import parser_registry


class GetInterfaceStatusHpeDnaParser(BaseParser[InterfaceStatusData]):
    """
    Parser for HPE Comware ``display interface brief`` output.

    Real CLI output (ref: HPE Comware CLI Reference)::

        Brief information on interfaces in route mode:
        Link: ADM - administratively down; Stby - standby
        Speed: (a) - auto
        Duplex: (a)/A - auto; H - half; F - full
        Type: A - access; T - trunk; H - hybrid
        Interface            Link Speed   Duplex Type PVID Description
        GE1/0/1              UP   1G(a)   F(a)   A    1
        GE1/0/2              DOWN auto     A      A    1
        GE1/0/3              UP   100M     F      A    100
        XGE1/0/1             UP   10G(a)   F(a)   T    1
        BAGG1                UP   20G(a)   F(a)   T    1
        ...

    Notes:
        - Speed: ``1G(a)``, ``100M``, ``10G(a)``, ``auto``
        - Duplex: ``F(a)``, ``F``, ``H``, ``A``
        - Link: ``UP``, ``DOWN``, ``ADM``
        - Interfaces: GE, XGE, FGE, BAGG, MGE, etc.
    """

    device_type = DeviceType.HPE
    command = "get_interface_status_hpe_dna"

    # Match interface lines in the brief table
    # Interface            Link Speed   Duplex Type PVID Description
    # GE1/0/1              UP   1G(a)   F(a)   A    1
    LINE_PATTERN = re.compile(
        r"^(?P<intf>\S+)"
        r"\s+(?P<link>UP|DOWN|ADM|Stby)"
        r"\s+(?P<speed>\S+)"
        r"\s+(?P<duplex>\S+)"
        r"\s+\S+"           # Type column
        r"\s+\d+",          # PVID column
        re.IGNORECASE,
    )

    DUPLEX_MAP = {
        "f": "full",
        "f(a)": "full",
        "h": "half",
        "h(a)": "half",
        "a": "auto",
        "a(a)": "auto",
    }

    LINK_MAP = {
        "up": "up",
        "down": "down",
        "adm": "down",
        "stby": "down",
    }

    def parse(self, raw_output: str) -> list[InterfaceStatusData]:
        if not raw_output or not raw_output.strip():
            return []

        results: list[InterfaceStatusData] = []

        for line in raw_output.splitlines():
            match = self.LINE_PATTERN.match(line.strip())
            if not match:
                continue

            intf = match.group("intf")
            link_raw = match.group("link").lower()
            speed_raw = match.group("speed")
            duplex_raw = match.group("duplex").lower()

            link_status = self.LINK_MAP.get(link_raw, "unknown")
            duplex = self.DUPLEX_MAP.get(duplex_raw, duplex_raw)
            speed = self._normalize_speed(speed_raw)

            results.append(InterfaceStatusData(
                interface_name=intf,
                link_status=link_status,
                speed=speed,
                duplex=duplex,
            ))

        return results

    def _normalize_speed(self, speed_raw: str) -> str | None:
        """Normalize speed string."""
        s = speed_raw.lower().rstrip(")")
        s = s.replace("(a", "")  # Remove auto indicator
        if s == "auto" or s == "--":
            return None
        # Map common values: 1g→1000M, 10g→10G, 100m→100M
        speed_map = {
            "1g": "1000M",
            "10g": "10G",
            "25g": "25G",
            "40g": "40G",
            "100g": "100G",
            "100m": "100M",
            "10m": "10M",
        }
        return speed_map.get(s, speed_raw)


# Register parser
parser_registry.register(GetInterfaceStatusHpeDnaParser())
