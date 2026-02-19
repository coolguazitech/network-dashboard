"""
Parser for 'get_interface_status_nxos_dna' API.

Parses Cisco NX-OS `show interface status` output to extract
interface link status, speed, and duplex information.

Real CLI command: show interface status
Platforms: Nexus 9000, 7000, 5000 series

=== ParsedData Model (DO NOT REMOVE) ===
class InterfaceStatusData(ParsedData):
    interface_name: str                      # interface name
    link_status: str                         # normalized to LinkStatus enum
    speed: str | None = None                 # speed string (e.g., "1000M")
    duplex: str | None = None                # normalized to DuplexMode enum
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show interface status
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceStatusData
from app.parsers.registry import parser_registry


class GetInterfaceStatusNxosDnaParser(BaseParser[InterfaceStatusData]):
    """
    Parser for Cisco NX-OS ``show interface status`` output.

    Real CLI output (ref: NTC-templates ``cisco_nxos_show_interface_status.raw``)::

        --------------------------------------------------------------------------------
        Port          Name               Status    Vlan      Duplex  Speed   Type
        --------------------------------------------------------------------------------
        Eth1/1        Server-01          connected 100       full    1000    1000base-T
        Eth1/2                           notconnec 1         auto    auto    1000base-T
        Eth1/3        Uplink-Core        connected trunk     full    10G     10Gbase-SR
        Eth1/4                           sfpAbsent 1         auto    auto    --
        Eth1/5                           xcvrAbsen 1         auto    auto    --
        Eth1/6        disabled-port      disabled  1         auto    auto    1000base-T
        Po1           Core-Uplink        connected trunk     full    10G     --
        ...

    Notes:
        - Status: ``connected``, ``notconnec``, ``disabled``, ``sfpAbsent``,
          ``xcvrAbsen``, ``linkFlapE``, ``errDisabl``
        - Duplex: ``full``, ``half``, ``auto``
        - Speed: ``1000``, ``10G``, ``auto``
        - Interfaces: Eth, Po, mgmt, Lo, etc.
    """

    device_type = DeviceType.CISCO_NXOS
    command = "get_interface_status_nxos_dna"

    # Match interface status lines (NX-OS uses fixed-width-ish columns)
    # Port          Name               Status    Vlan      Duplex  Speed   Type
    # Eth1/1        Server-01          connected 100       full    1000    1000base-T
    LINE_PATTERN = re.compile(
        r"^(?P<port>(?:Eth|Po|mgmt|Lo)\S+)"
        r"\s+"
        r"(?P<name>.*?)"
        r"\s+(?P<status>connected|notconnec|disabled|sfpAbsent|xcvrAbsen|linkFlapE|errDisabl|inactive|noOperMem)"
        r"\s+(?P<vlan>\S+)"
        r"\s+(?P<duplex>\S+)"
        r"\s+(?P<speed>\S+)",
        re.IGNORECASE,
    )

    STATUS_MAP = {
        "connected": "up",
        "notconnec": "down",
        "disabled": "down",
        "sfpabsent": "down",
        "xcvrabsen": "down",
        "linkflape": "down",
        "errdisabl": "down",
        "inactive": "down",
        "noopermem": "down",
    }

    def parse(self, raw_output: str) -> list[InterfaceStatusData]:
        if not raw_output or not raw_output.strip():
            return []

        results: list[InterfaceStatusData] = []

        for line in raw_output.splitlines():
            match = self.LINE_PATTERN.match(line.strip())
            if not match:
                continue

            port = match.group("port")
            status_raw = match.group("status").lower()
            duplex_raw = match.group("duplex").lower()
            speed_raw = match.group("speed")

            link_status = self.STATUS_MAP.get(status_raw, "unknown")
            duplex = self._normalize_duplex(duplex_raw)
            speed = self._normalize_speed(speed_raw)

            results.append(InterfaceStatusData(
                interface_name=port,
                link_status=link_status,
                speed=speed,
                duplex=duplex,
            ))

        return results

    def _normalize_duplex(self, duplex_raw: str) -> str | None:
        """Normalize duplex value."""
        if duplex_raw in ("full",):
            return "full"
        if duplex_raw in ("half",):
            return "half"
        if duplex_raw == "auto":
            return None
        return duplex_raw

    def _normalize_speed(self, speed_raw: str) -> str | None:
        """Normalize speed value."""
        s = speed_raw.lower()
        if s in ("auto", "--"):
            return None
        speed_map = {
            "10": "10M",
            "100": "100M",
            "1000": "1000M",
            "2500": "2500M",
            "5000": "5000M",
            "10g": "10G",
            "25g": "25G",
            "40g": "40G",
            "100g": "100G",
        }
        return speed_map.get(s, speed_raw)


# Register parser
parser_registry.register(GetInterfaceStatusNxosDnaParser())
