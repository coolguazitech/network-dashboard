"""Mock: Uplink \u9130\u5c45\uff08CDP/LLDP\uff09(get_uplink)\u3002"""
from __future__ import annotations

from mock_server.convergence import should_device_fail


_DEFAULT_NEIGHBORS: list[tuple[str, str, str]] = [
    ("GigabitEthernet1/0/49", "SW-DEFAULT-CORE-01", "HGE1/0/1"),
    ("GigabitEthernet1/0/50", "SW-DEFAULT-CORE-02", "HGE1/0/1"),
]


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    *,
    switch_ip: str = "",
    expected_neighbors: list[tuple[str, str, str]] | None = None,
) -> str:
    fails = should_device_fail(is_old, active_seconds, converge_time)

    # 使用 DB 中的期望鄰居（收斂後應出現正確鄰居）
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
