"""Mock: Client IP Ping (gnms_ping)。

接收逗號分隔的 client IP，回傳 CSV 格式的 ping 結果。
每個 client IP 獨立、確定性地判斷可達性。
"""
from __future__ import annotations

import hashlib


def generate(
    device_type: str,
    fails: bool = False,
    switch_ips: str | None = None,
    failure_rate: float = 0.05,
    **_kw: object,
) -> str:
    """
    產出 CSV 格式的 client ping 結果。

    switch_ips 是逗號分隔的 client IP 字串。
    每個 client IP 用 hash 獨立、確定性地決定是否可達。
    """
    if not switch_ips:
        return "IP,Reachable,Latency_ms\n"

    ips = [ip.strip() for ip in switch_ips.split(",") if ip.strip()]
    if not ips:
        return "IP,Reachable,Latency_ms\n"

    lines = ["IP,Reachable,Latency_ms"]
    for ip in ips:
        ip_hash = int(hashlib.md5(ip.encode()).hexdigest(), 16)
        p = (ip_hash % 10000) / 10000.0
        if p < failure_rate:
            lines.append(f"{ip},False,0")
        else:
            latency = round(1.0 + (ip_hash % 40) / 10.0, 1)
            lines.append(f"{ip},True,{latency}")
    return "\n".join(lines)
