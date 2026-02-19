"""
Steady-state mock mode — 穩態模擬。

不使用時間收斂邏輯，所有設備視為已上線運作。
小比例的設備+API 組合會有持續性故障（不會 flapping）。

故障是確定性的（基於 switch_ip + api_name 的 hash），
並在不同時間點出現（避免一次全部爆發）。
一旦出現，故障將持續存在。
"""
from __future__ import annotations

import hashlib


def _deterministic_float(switch_ip: str, api_name: str, salt: str = "") -> float:
    """Return a deterministic value in [0, 1) for a device+API combo."""
    key = f"{switch_ip}:{api_name}:{salt}"
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return (h % 10000) / 10000.0


def should_fail_steady(
    switch_ip: str,
    api_name: str,
    active_seconds: float,
    failure_rate: float = 0.05,
    onset_range: float = 3600.0,
) -> bool:
    """
    判斷指定設備+API 是否應產生故障資料。

    ~failure_rate 的設備+API 組合會故障。
    故障在 [0, onset_range] 秒內分散出現，出現後持續不變。

    Args:
        switch_ip: 設備 IP
        api_name: API 名稱（如 "get_fan"）
        active_seconds: 歲修啟動後的累計秒數
        failure_rate: 會故障的組合比例（預設 5%）
        onset_range: 故障出現時間分散在多少秒內

    Returns:
        True = 此設備+API 應產生故障資料
    """
    # 確定性選擇：只有 failure_rate 比例的組合會故障
    p = _deterministic_float(switch_ip, api_name)
    if p >= failure_rate:
        return False

    # 分散起始時間：每個故障在不同時間點出現
    onset = _deterministic_float(switch_ip, api_name, "onset") * onset_range
    return active_seconds >= onset
