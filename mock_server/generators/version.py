"""Mock: \u97cc\u9ad4\u7248\u672c\u8cc7\u8a0a (get_version)\u3002"""
from __future__ import annotations


def generate(device_type: str, fails: bool = False, **_kw: object) -> str:
    if device_type == "nxos":
        return _generate_nxos(fails)
    elif device_type == "ios":
        return _generate_ios(fails)
    else:
        return _generate_hpe(fails)


def _generate_hpe(fails: bool) -> str:
    release = "6635P05" if fails else "6635P07"
    return (
        "HPE Comware Platform Software\n"
        f"Comware Software, Version 7.1.070, Release {release}\n"
        "Copyright (c) 2010-2024 Hewlett Packard Enterprise "
        "Development LP\n"
        "HPE FF 5710 48SFP+ 6QS 2SL Switch\n"
        "Uptime is 0 weeks, 1 day, 3 hours, 22 minutes\n"
    )


def _generate_nxos(fails: bool) -> str:
    ver = "9.3.8" if fails else "10.3.3"
    return (
        "Cisco Nexus Operating System (NX-OS) Software\n"
        "TAC support: http://www.cisco.com/tac\n"
        "Copyright (c) 2002-2024, Cisco Systems, Inc.\n"
        f"NXOS: version {ver}\n"
        "Hardware\n"
        "  cisco Nexus9000 C9336C-FX2 Chassis\n"
        "Uptime is 0 weeks, 1 day, 3 hours\n"
    )


def _generate_ios(fails: bool) -> str:
    ver = "16.12.4" if fails else "17.9.4"
    return (
        f"Cisco IOS Software, Version {ver}\n"
        "Copyright (c) 1986-2024 by Cisco Systems, Inc.\n"
        "Cisco Catalyst C9200L-48P-4G Switch\n"
        "Uptime is 0 weeks, 1 day, 3 hours\n"
    )
