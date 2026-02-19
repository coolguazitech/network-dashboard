"""Mock: Port-Channel / LAG \u72c0\u614b (get_channel_group)\u3002"""
from __future__ import annotations

from mock_server.convergence import should_device_fail


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    *,
    switch_ip: str = "",
) -> str:
    fails = should_device_fail(is_old, active_seconds, converge_time)

    parts = switch_ip.split(".")
    third_octet = int(parts[2]) if len(parts) == 4 else 0

    if device_type == "nxos":
        return _generate_nxos(fails, third_octet)
    elif device_type == "ios":
        return _generate_ios(fails, third_octet)
    else:
        return _generate_hpe(fails, third_octet)


def _generate_hpe(fails: bool, third_octet: int) -> str:
    m1_status = "U" if fails else "S"
    if third_octet == 20:
        m1, m2 = "HGE1/0/25", "HGE1/0/26"
    else:
        m1, m2 = "XGE1/0/51", "XGE1/0/52"
    lines = [
        "AggID   Interface   Link   Attribute   Mode   Members",
        (
            f"1       BAGG1       UP     A           LACP   "
            f"{m1}({m1_status}) {m2}(S)"
        ),
    ]
    return "\n".join(lines)


def _generate_nxos(fails: bool, third_octet: int) -> str:
    m1_flag = "D" if fails else "P"
    if third_octet == 20:
        m1, m2 = "Eth1/25", "Eth1/26"
    else:
        m1, m2 = "Eth1/51", "Eth1/52"
    pc_status = "SD" if fails else "SU"
    lines = [
        "--------------------------------------------------------------------------------",
        "Group Port-       Type     Protocol  Member Ports",
        "      Channel",
        "--------------------------------------------------------------------------------",
        f"1     Po1({pc_status})     Eth      LACP      {m1}({m1_flag})    {m2}(P)",
    ]
    return "\n".join(lines)


def _generate_ios(fails: bool, third_octet: int) -> str:
    m1_flag = "D" if fails else "P"
    if third_octet == 20:
        m1, m2 = "Gi1/0/25", "Gi1/0/26"
    else:
        m1, m2 = "Gi1/0/51", "Gi1/0/52"
    pc_status = "SD" if fails else "SU"
    lines = [
        "Group  Port-channel  Protocol    Ports",
        "------+-------------+-----------+-------",
        f"1      Po1({pc_status})       LACP        {m1}({m1_flag}) {m2}(P)",
    ]
    return "\n".join(lines)
