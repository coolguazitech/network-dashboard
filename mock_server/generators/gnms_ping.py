"""Mock: Client IP Ping (gnms_ping)。

接收逗號分隔的 client IP，回傳 CSV 格式的 ping 結果。

兩種模式：
  - 收斂模式：elapsed 越久，可達比例越高；設備不可達則所有 client 也不可達
  - 穩態模式：每個 client IP 獨立判斷可達性（與設備可達性無關）
"""
from __future__ import annotations

import hashlib

from mock_server.convergence import should_device_fail


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    switch_ips: str | None = None,
    steady_state_failure_rate: float = 0.0,
    **_kw: object,
) -> str:
    """
    產出 CSV 格式的 client ping 結果。

    switch_ips 是逗號分隔的 client IP 字串。

    steady_state_failure_rate > 0 時使用穩態邏輯：
    每個 client IP 獨立、確定性地決定是否可達，與設備狀態無關。
    """
    if not switch_ips:
        return "IP,Reachable,Latency_ms\n"

    ips = [ip.strip() for ip in switch_ips.split(",") if ip.strip()]
    if not ips:
        return "IP,Reachable,Latency_ms\n"

    lines = ["IP,Reachable,Latency_ms"]

    if steady_state_failure_rate > 0:
        # ── 穩態模式：每個 client IP 獨立判斷 ──
        for ip in ips:
            ip_hash = int(hashlib.md5(ip.encode()).hexdigest(), 16)
            p = (ip_hash % 10000) / 10000.0
            if p < steady_state_failure_rate:
                lines.append(f"{ip},False,0")
            else:
                latency = round(1.0 + (ip_hash % 40) / 10.0, 1)
                lines.append(f"{ip},True,{latency}")
        return "\n".join(lines)

    # ── 收斂模式（原始邏輯）──
    # 基本判斷：設備不可達時所有 client 也不可達
    device_fails = should_device_fail(is_old, active_seconds, converge_time)
    if device_fails:
        for ip in ips:
            lines.append(f"{ip},False,0")
        return "\n".join(lines)

    # 設備可達後，根據每個 IP 的 hash 產生不同的收斂時間偏移
    # 讓部分 client 先可達、部分後可達
    switch_time = converge_time / 2 if converge_time > 0 else 0
    for ip in ips:
        ip_hash = int(hashlib.md5(ip.encode()).hexdigest()[:8], 16)
        # 每個 IP 有 ±30% 的收斂偏移
        offset_ratio = (ip_hash % 60 - 30) / 100.0  # -0.30 ~ +0.29
        ip_switch_time = switch_time * (1.0 + offset_ratio)

        if active_seconds >= ip_switch_time:
            reachable = True
            # 模擬延遲：1~5ms
            latency = round(1.0 + (ip_hash % 40) / 10.0, 1)
        else:
            reachable = False
            latency = 0

        lines.append(f"{ip},{reachable},{latency}")

    return "\n".join(lines)
