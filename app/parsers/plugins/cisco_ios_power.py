"""
Cisco IOS Power Supply Parser — 解析 Cisco IOS 電源供應器狀態。

CLI 指令：show power（或 show environment power）
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "power"

輸出模型：list[PowerData]
    PowerData 欄位：
        ps_id: str                    — 電源 ID（如 "PS1", "PS2"）
        status: str                   — 自動正規化為 OperationalStatus 枚舉值
        input_status: str | None      — IOS 簡化格式不提供，為 None
        output_status: str | None     — IOS 簡化格式不提供，為 None
        capacity_watts: float | None  — IOS 簡化格式不提供，為 None
        actual_output_watts: float|None — IOS 簡化格式不提供，為 None
"""

from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class CiscoIosPowerParser(BaseParser[PowerData]):
    """
    Cisco IOS 電源供應器 Parser。

    CLI 指令：show power

    輸入格式（raw_output 範例）：
    ::

        PS1 is OK
        PS2 is NOT OK

    或較詳細的格式：
    ::

        Main Power Supply:
        PS1 is OK

        Redundant Power Supply:
        PS2 is OK

    輸出格式（parse() 回傳值）：
    ::

        [
            PowerData(ps_id="PS1", status="ok", capacity_watts=None,
                      actual_output_watts=None, input_status=None, output_status=None),
            PowerData(ps_id="PS2", status="fail", capacity_watts=None,
                      actual_output_watts=None, input_status=None, output_status=None),
        ]

    解析策略：
        - 用 regex 匹配 "PSN is XXX" 格式（N 為數字）
        - "OK" → status="ok"
        - 其他值（"NOT OK", "NOT PRESENT"）→ status="fail"
        - 此指令不提供瓦數/電流等詳細資訊 → capacity 和 output 均為 None

    已知邊界情況：
        - 不同 Catalyst 型號的 show power 格式差異較大
          某些型號會顯示表格（含瓦數），此 parser 目前只處理簡單格式
        - show environment power 和 show power 的輸出可能不同
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "power"
    command = "show power"

    def parse(self, raw_output: str) -> list[PowerData]:
        """
        Parse IOS power status output.

        Example:
        PS1 is OK
        PS2 is NOT OK
        """
        results: list[PowerData] = []

        pattern = re.compile(
            r"^(PS\d+)\s+is\s+(.+)$",
            re.IGNORECASE | re.MULTILINE,
        )

        for match in pattern.finditer(raw_output):
            ps_id = match.group(1)
            raw_status = match.group(2).strip()
            status = "ok" if raw_status.upper() == "OK" else "fail"

            results.append(
                PowerData(
                    ps_id=ps_id,
                    status=status,
                    capacity_watts=None,
                    actual_output_watts=None,
                    input_status=None,
                    output_status=None,
                )
            )

        return results


parser_registry.register(CiscoIosPowerParser())
