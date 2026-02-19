"""
Parser for 'get_interface_status_ios_dna' API.

Parses Cisco IOS/IOS-XE `show interfaces status` output to extract
interface link status, speed, and duplex information.

Real CLI command: show interfaces status
Platforms: Catalyst 2960, 3560, 3750, 3850, 9200, 9300, 9500

=== ParsedData Model (DO NOT REMOVE) ===
class InterfaceStatusData(ParsedData):
    interface_name: str                      # interface name
    link_status: str                         # normalized to LinkStatus enum
    speed: str | None = None                 # speed string (e.g., "1000M")
    duplex: str | None = None                # normalized to DuplexMode enum
=== End ParsedData Model ===

=== Real CLI Command ===
Command: show interfaces status
=== End Real CLI Command ===
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceStatusData
from app.parsers.registry import parser_registry


class GetInterfaceStatusIosDnaParser(BaseParser[InterfaceStatusData]):
    """
    Parser for Cisco IOS/IOS-XE ``show interfaces status`` output.

    Real CLI output (ref: NTC-templates)::

        Port      Name               Status       Vlan       Duplex  Speed Type
        Gi1/0/1                      connected    1          a-full  a-1000 10/100/1000BaseTX
        Gi1/0/2   Server-01          connected    100        full    1000   10/100/1000BaseTX
        Gi1/0/3                      notconnect   1          auto    auto   10/100/1000BaseTX
        Gi1/0/4   AP-Floor2          disabled     1          auto    auto   10/100/1000BaseTX
        Te1/1/1                      connected    trunk      full    10G    SFP-10GBase-SR
        Po1       Uplink-Core        connected    trunk      a-full  10G
        ...

    IOS-XE (C9300) variant::

        Port         Name               Status       Vlan       Duplex  Speed Type
        Gi1/0/1      USER-PC            connected    10         a-full  a-1000 10/100/1000BaseTX
        Tw1/0/1                         connected    1          a-full  a-100M 100/1000/2.5GBaseTX
        Te1/1/1                         connected    trunk      full    10G    SFP-10GBase-SR

    Notes:
        - Status: ``connected``, ``notconnect``, ``disabled``, ``err-disabled``
        - Duplex: ``a-full``, ``full``, ``a-half``, ``half``, ``auto``
        - Speed: ``a-1000``, ``1000``, ``10G``, ``auto``, ``a-100M``
        - Interfaces: Gi, Te, Tw, Fo, Po, etc.
    """

    device_type = DeviceType.CISCO_IOS
    command = "get_interface_status_ios_dna"

    # Match interface status lines
    # Port      Name               Status       Vlan       Duplex  Speed Type
    # Gi1/0/1                      connected    1          a-full  a-1000 10/100/1000BaseTX
    LINE_PATTERN = re.compile(
        r"^(?P<port>\S+)"
        r"\s+"
        r"(?P<name>.*?)"
        r"\s+(?P<status>connected|notconnect|disabled|err-disabled|inactive|monitoring)"
        r"\s+(?P<vlan>\S+)"
        r"\s+(?P<duplex>\S+)"
        r"\s+(?P<speed>\S+)",
        re.IGNORECASE,
    )

    STATUS_MAP = {
        "connected": "up",
        "notconnect": "down",
        "disabled": "down",
        "err-disabled": "down",
        "inactive": "down",
        "monitoring": "up",
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
        d = duplex_raw.replace("a-", "")  # Strip auto-negotiated prefix
        if d in ("full",):
            return "full"
        if d in ("half",):
            return "half"
        if d == "auto":
            return None
        return d

    def _normalize_speed(self, speed_raw: str) -> str | None:
        """Normalize speed value."""
        s = speed_raw.lower().replace("a-", "")  # Strip auto prefix
        if s == "auto":
            return None
        # Map common values
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
            "100m": "100M",
            "1000m": "1000M",
        }
        return speed_map.get(s, speed_raw)


# Register parser
parser_registry.register(GetInterfaceStatusIosDnaParser())
