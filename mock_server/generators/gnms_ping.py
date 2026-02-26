"""Mock: Client IP Ping (gnms_ping)。

接收逗號分隔的 client IP，回傳 CSV 格式的 ping 結果。
每個 client IP 獨立、隨機地判斷可達性（per-IP per-cycle）。
"""
from __future__ import annotations

import random

from mock_server.generators._probabilities import PING_FAIL_PROB


def generate(
    device_type: str,
    fails: bool = False,
    switch_ips: str | None = None,
    failure_rate: float = PING_FAIL_PROB,
    **_kw: object,
) -> str:
    """
    產出 CSV 格式的 client ping 結果。

    switch_ips 是逗號分隔的 client IP 字串。
    每個 client IP 用 random.random() 獨立決定是否可達（per-cycle 隨機）。
    """
    if not switch_ips:
        return "IP,Reachable,Latency_ms\n"

    ips = [ip.strip() for ip in switch_ips.split(",") if ip.strip()]
    if not ips:
        return "IP,Reachable,Latency_ms\n"

    lines = ["IP,Reachable,Latency_ms"]
    for ip in ips:
        # per-IP 隨機可達性判斷
        if random.random() < failure_rate:
            lines.append(f"{ip},False,0")
        else:
            latency = round(1.0 + random.random() * 4.0, 1)
            lines.append(f"{ip},True,{latency}")
    return "\n".join(lines)
