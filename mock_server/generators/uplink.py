"""Mock: Uplink 鄰居（CDP/LLDP）(get_uplink_lldp / get_uplink_cdp)。"""
from __future__ import annotations


_DEFAULT_NEIGHBORS: list[tuple[str, str, str]] = [
    ("GigabitEthernet1/0/49", "SW-DEFAULT-CORE-01", "HGE1/0/1"),
    ("GigabitEthernet1/0/50", "SW-DEFAULT-CORE-02", "HGE1/0/1"),
]


def generate_lldp(
    device_type: str,
    fails: bool = False,
    *,
    switch_ip: str = "",
    expected_neighbors: list[tuple[str, str, str]] | None = None,
    **_kw: object,
) -> str:
    """Generate LLDP neighbor output (HPE / IOS / NXOS all support LLDP)."""
    neighbors = expected_neighbors if expected_neighbors else _DEFAULT_NEIGHBORS

    if fails and len(neighbors) > 1:
        neighbors = neighbors[:1]

    if device_type == "nxos":
        return _generate_nxos_lldp(neighbors)
    elif device_type == "ios":
        return _generate_ios_lldp(neighbors)
    else:
        return _generate_hpe_lldp(neighbors, switch_ip)


def generate_cdp(
    device_type: str,
    fails: bool = False,
    *,
    expected_neighbors: list[tuple[str, str, str]] | None = None,
    **_kw: object,
) -> str:
    """Generate CDP neighbor output (Cisco IOS / NXOS only)."""
    neighbors = expected_neighbors if expected_neighbors else _DEFAULT_NEIGHBORS

    if fails and len(neighbors) > 1:
        neighbors = neighbors[:1]

    if device_type == "nxos":
        return _generate_nxos_cdp(neighbors)
    else:
        return _generate_cisco_cdp(neighbors)


# Keep legacy generate() for backwards compatibility with tests
def generate(
    device_type: str,
    fails: bool = False,
    *,
    switch_ip: str = "",
    expected_neighbors: list[tuple[str, str, str]] | None = None,
    **_kw: object,
) -> str:
    neighbors = expected_neighbors if expected_neighbors else _DEFAULT_NEIGHBORS

    if fails and len(neighbors) > 1:
        neighbors = neighbors[:1]

    if device_type == "nxos":
        return _generate_nxos_lldp(neighbors)
    elif device_type == "ios":
        return _generate_cisco_cdp(neighbors)
    else:
        return _generate_hpe_lldp(neighbors, switch_ip)


def _generate_hpe_lldp(
    neighbors: list[tuple[str, str, str]], switch_ip: str,
) -> str:
    lines: list[str] = []
    dev_num = int(switch_ip.split(".")[-1]) if switch_ip else 1
    for idx, (local_intf, remote_host, remote_intf) in enumerate(neighbors):
        port_num = idx + 1
        lines.append(
            f"LLDP neighbor-information of port {port_num} [{local_intf}]:"
        )
        lines.append("  LLDP neighbor index       : 1")
        lines.append("  Chassis type              : MAC address")
        lines.append(
            f"  Chassis ID                : 0012-3456-78{dev_num:02x}"
        )
        lines.append("  Port ID type              : Interface name")
        lines.append(f"  Port ID                   : {remote_intf}")
        lines.append(f"  System name               : {remote_host}")
        lines.append(
            "  System description        : HPE Comware Platform Software"
        )
        lines.append("")
    return "\n".join(lines)


def _generate_ios_lldp(neighbors: list[tuple[str, str, str]]) -> str:
    """Generate Cisco IOS `show lldp neighbors detail` format."""
    lines: list[str] = []
    for local_intf, remote_host, remote_intf in neighbors:
        lines.append("------------------------------------------------")
        lines.append(f"Local Intf: {local_intf}")
        lines.append("Chassis id: 0026.980a.3c01")
        lines.append(f"Port id: {remote_intf}")
        lines.append("Port Description: uplink")
        lines.append(f"System Name: {remote_host}")
        lines.append("")
        lines.append("System Description:")
        lines.append("Cisco IOS Software, Version 15.2(4)E10")
        lines.append("")
        lines.append("Time remaining: 102 seconds")
        lines.append("System Capabilities: B,R")
        lines.append("Enabled Capabilities: B,R")
        lines.append("")
    if neighbors:
        lines.append("------------------------------------------------")
    return "\n".join(lines)


def _generate_cisco_cdp(neighbors: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for local_intf, remote_host, remote_intf in neighbors:
        lines.append("-------------------------")
        lines.append(f"Device ID: {remote_host}")
        lines.append("Entry address(es):")
        lines.append("  IP address: 10.0.0.1")
        lines.append(
            "Platform: cisco WS-C3750X-48,  "
            "Capabilities: Router Switch IGMP"
        )
        lines.append(
            f"Interface: {local_intf},  "
            f"Port ID (outgoing port): {remote_intf}"
        )
        lines.append("Holdtime : 179 sec")
        lines.append("")
    if neighbors:
        lines.append("-------------------------")
    return "\n".join(lines)


def _generate_nxos_lldp(neighbors: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for local_intf, remote_host, remote_intf in neighbors:
        lines.append("Chassis id: 0012.3456.789a")
        lines.append(f"Port id: {remote_intf}")
        lines.append(f"Local Port id: {local_intf}")
        lines.append("Port Description: not advertised")
        lines.append(f"System Name: {remote_host}")
        lines.append(
            "System Description: "
            "Cisco Nexus Operating System (NX-OS) Software"
        )
        lines.append("Time remaining: 112 seconds")
        lines.append("")
    return "\n".join(lines)


def _generate_nxos_cdp(neighbors: list[tuple[str, str, str]]) -> str:
    """Generate Cisco NX-OS `show cdp neighbors detail` format."""
    lines: list[str] = []
    for local_intf, remote_host, remote_intf in neighbors:
        lines.append("----------------------------------------")
        lines.append(f"Device ID:{remote_host}(SSI12345678)")
        lines.append(f"System Name: {remote_host}")
        lines.append("")
        lines.append("Interface address(es):")
        lines.append("    IPv4 Address: 10.0.0.1")
        lines.append(
            "Platform: N9K-C93180YC-EX, "
            "Capabilities: Router Switch IGMP Filtering"
        )
        lines.append(
            f"Interface: {local_intf}, "
            f"Port ID (outgoing port): {remote_intf}"
        )
        lines.append("Holdtime: 155 sec")
        lines.append("")
    if neighbors:
        lines.append("----------------------------------------")
    return "\n".join(lines)
