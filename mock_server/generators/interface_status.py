"""Mock: 介面狀態 (get_interface_status)。"""
from __future__ import annotations

from mock_server.convergence import should_device_fail

# 20 個介面，涵蓋不同類型
_HPE_INTERFACES = [
    ("GE1/0/1", 1), ("GE1/0/2", 1), ("GE1/0/3", 100),
    ("GE1/0/4", 100), ("GE1/0/5", 200), ("GE1/0/6", 200),
    ("GE1/0/7", 10), ("GE1/0/8", 10), ("GE1/0/9", 1),
    ("GE1/0/10", 1), ("GE1/0/11", 1), ("GE1/0/12", 1),
    ("GE1/0/13", 1), ("GE1/0/14", 1), ("GE1/0/15", 1),
    ("GE1/0/16", 1), ("GE1/0/17", 1), ("GE1/0/18", 1),
    ("XGE1/0/1", 1), ("BAGG1", 1),
]

_IOS_INTERFACES = [
    ("Gi1/0/1", 1), ("Gi1/0/2", 1), ("Gi1/0/3", 100),
    ("Gi1/0/4", 100), ("Gi1/0/5", 200), ("Gi1/0/6", 200),
    ("Gi1/0/7", 10), ("Gi1/0/8", 10), ("Gi1/0/9", 1),
    ("Gi1/0/10", 1), ("Gi1/0/11", 1), ("Gi1/0/12", 1),
    ("Gi1/0/13", 1), ("Gi1/0/14", 1), ("Gi1/0/15", 1),
    ("Gi1/0/16", 1), ("Gi1/0/17", 1), ("Gi1/0/18", 1),
    ("Te1/1/1", 1), ("Po1", 1),
]

_NXOS_INTERFACES = [
    ("Eth1/1", 1), ("Eth1/2", 1), ("Eth1/3", 100),
    ("Eth1/4", 100), ("Eth1/5", 200), ("Eth1/6", 200),
    ("Eth1/7", 10), ("Eth1/8", 10), ("Eth1/9", 1),
    ("Eth1/10", 1), ("Eth1/11", 1), ("Eth1/12", 1),
    ("Eth1/13", 1), ("Eth1/14", 1), ("Eth1/15", 1),
    ("Eth1/16", 1), ("Eth1/17", 1), ("Eth1/18", 1),
    ("Eth1/49", 1), ("Po1", 1),
]


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    **_kw: object,
) -> str:
    fails = should_device_fail(is_old, active_seconds, converge_time)

    if device_type == "nxos":
        return _generate_nxos(fails)
    elif device_type == "ios":
        return _generate_ios(fails)
    else:
        return _generate_hpe(fails)


def _generate_hpe(fails: bool) -> str:
    lines = [
        "Brief information on interfaces in route mode:",
        "Link: ADM - administratively down; Stby - standby",
        "Speed: (a) - auto",
        "Duplex: (a)/A - auto; H - half; F - full",
        "Type: A - access; T - trunk; H - hybrid",
        f"{'Interface':<20} {'Link':<5}{'Speed':<8}{'Duplex':<7}{'Type':<5}{'PVID':<5}Description",
    ]
    for i, (intf, pvid) in enumerate(_HPE_INTERFACES):
        if fails and i in (2, 3, 4):
            link, speed, duplex = "DOWN", "auto", "A"
        elif intf.startswith("XGE") or intf.startswith("BAGG"):
            link, speed, duplex = "UP", "10G(a)", "F(a)"
        else:
            link, speed, duplex = "UP", "1G(a)", "F(a)"
        intf_type = "T" if intf.startswith(("XGE", "BAGG")) else "A"
        lines.append(
            f"{intf:<20} {link:<5}{speed:<8}{duplex:<7}{intf_type:<5}{pvid}"
        )
    return "\n".join(lines)


def _generate_ios(fails: bool) -> str:
    lines = [
        f"{'Port':<14}{'Name':<19}{'Status':<13}{'Vlan':<11}{'Duplex':<8}{'Speed':<7}Type",
    ]
    for i, (intf, vlan) in enumerate(_IOS_INTERFACES):
        if fails and i in (2, 3, 4):
            status, duplex, speed = "notconnect", "auto", "auto"
        elif intf.startswith("Te") or intf.startswith("Po"):
            status, duplex, speed = "connected", "full", "10G"
            vlan = "trunk"
        else:
            status, duplex, speed = "connected", "a-full", "a-1000"
        name = ""
        vlan_str = str(vlan) if isinstance(vlan, int) else vlan
        lines.append(
            f"{intf:<14}{name:<19}{status:<13}{vlan_str:<11}{duplex:<8}{speed:<7}10/100/1000BaseTX"
        )
    return "\n".join(lines)


def _generate_nxos(fails: bool) -> str:
    lines = [
        f"{'Port':<14}{'Name':<19}{'Status':<10}{'Vlan':<10}{'Duplex':<8}{'Speed':<8}Type",
    ]
    for i, (intf, vlan) in enumerate(_NXOS_INTERFACES):
        if fails and i in (2, 3, 4):
            status, duplex, speed = "notconnec", "auto", "auto"
        elif intf == "Eth1/49" or intf.startswith("Po"):
            status, duplex, speed = "connected", "full", "10G"
            vlan = "trunk"
        else:
            status, duplex, speed = "connected", "full", "1000"
        vlan_str = str(vlan) if isinstance(vlan, int) else vlan
        lines.append(
            f"{intf:<14}{'':<19}{status:<10}{vlan_str:<10}{duplex:<8}{speed:<8}1000base-T"
        )
    return "\n".join(lines)
