"""
Generic Ping Parser — 解析各平台的 Ping 結果（跨廠牌通用邏輯）。

device_type = None（通用 Parser，適用所有設備類型）。
Registry 查詢時若無精確匹配，會 fallback 到此 generic parser。

indicator_type = "ping"

輸出模型：list[PingData]（通常只有一筆）
    PingData 欄位：
        target: str           — Ping 目標（此 parser 固定為 "self"）
        is_reachable: bool    — 是否可達（success_rate > 0 即為 True）
        success_rate: float   — 成功率 0.0 ~ 100.0（百分比）
        avg_rtt_ms: float|None — 平均往返時間 (ms)

設計說明：
    Ping 的輸出格式在 Linux、Cisco IOS、Cisco NX-OS、HPE Comware 上相同
    （都是 "X packets transmitted, Y received, Z% packet loss"）。
    因此註冊為 generic parser（device_type=None），一次覆蓋所有設備類型。
    若未來某廠牌 ping 格式不同，只需新增該廠牌的 device-specific parser，
    精確匹配會優先於 generic fallback。
"""
from __future__ import annotations

import re

from app.parsers.protocols import BaseParser, PingData
from app.parsers.registry import parser_registry


class PingParser(BaseParser[PingData]):
    """
    Generic Ping Parser — 適用所有設備類型。

    CLI 指令：ping {target_ip}（由系統自動帶入目標 IP）

    輸入格式（raw_output 範例 — Linux/Cisco 格式）：
    ::

        PING 10.0.1.1 (10.0.1.1) 56(84) bytes of data.
        64 bytes from 10.0.1.1: icmp_seq=1 ttl=254 time=1.23 ms

        --- 10.0.1.1 ping statistics ---
        5 packets transmitted, 5 packets received, 0.0% packet loss
        round-trip min/avg/max = 1.15/1.19/1.23 ms

    或 Windows 格式：
    ::

        Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)

    解析策略：
        1. 匹配 "X% packet loss" → 計算 success_rate = 100 - X
        2. 若沒匹配到，嘗試 Windows 格式 "(X% loss)"
        3. 匹配 "min/avg/max = .../AVG/..." → 取 avg_rtt_ms
        4. success_rate > 0 → is_reachable = True

    已知邊界情況：
        - target 固定為 "self"（此 parser 不解析目標 IP）
        - 此 parser 永遠回傳一筆 PingData（即使解析失敗，也回傳 success_rate=0）
        - 不同於其他 parser，ping parser 不會回傳空列表
        - Windows 格式和 Linux/Cisco 格式都支援
    """

    device_type = None  # Generic: works for all device types
    indicator_type = "ping"
    command = "ping"

    def parse(self, raw_output: str) -> list[PingData]:
        success_rate = 0.0
        is_reachable = False
        avg_rtt = None

        # Linux/Cisco style: "X% packet loss"
        loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", raw_output)
        if loss_match:
            loss_pct = float(loss_match.group(1))
            success_rate = 100.0 - loss_pct
        else:
            # Windows style: "(X% loss)"
            loss_match_win = re.search(r"\((\d+)% loss\)", raw_output)
            if loss_match_win:
                loss_pct = float(loss_match_win.group(1))
                success_rate = 100.0 - loss_pct

        # Match RTT (min/avg/max)
        rtt_match = re.search(
            r"min/avg/max.*?=\s*[\d\.]+/([\d\.]+)/[\d\.]+", raw_output,
        )
        if rtt_match:
            avg_rtt = float(rtt_match.group(1))

        if success_rate > 0:
            is_reachable = True

        return [
            PingData(
                target="self",
                is_reachable=is_reachable,
                success_rate=success_rate,
                avg_rtt_ms=avg_rtt,
            )
        ]


# Register once as generic (device_type=None)
parser_registry.register(PingParser())
