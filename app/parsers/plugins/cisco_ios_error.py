"""
Cisco IOS Interface Error Parser — 解析 Cisco IOS 介面錯誤計數器。

CLI 指令：show interfaces counters errors
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "error_count"

輸出模型：list[InterfaceErrorData]
    InterfaceErrorData 欄位：
        interface_name: str    — 介面名稱（如 "Gi1/0/1"）
        crc_errors: int        — CRC 錯誤計數（此 parser 固定為 0，IOS 格式不細分）
        input_errors: int      — 輸入錯誤計數
        output_errors: int     — 輸出錯誤計數
        collisions: int        — 碰撞計數（預設 0）
        giants: int            — 超大封包計數（預設 0）
        runts: int             — 過小封包計數（預設 0）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class CiscoIosErrorParser(BaseParser[InterfaceErrorData]):
    """
    Cisco IOS 介面錯誤計數器 Parser。

    CLI 指令：show interfaces counters errors

    輸入格式（raw_output 範例）：
    ::

        Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        Gi1/0/1               0          0          0          0          0           0
        Gi1/0/2               0          5          0          2          0           0
        Gi1/0/3               0          0          1          0          0           0

    或簡化格式（某些 IOS 版本）：
    ::

        Interface            Input(errs)       Output(errs)
        Gi1/0/1                        0                  0
        Gi1/0/2                        5                  2

    輸出格式（parse() 回傳值）：
    ::

        [
            InterfaceErrorData(interface_name="Gi1/0/1", crc_errors=0,
                              input_errors=0, output_errors=0),
            InterfaceErrorData(interface_name="Gi1/0/2", crc_errors=0,
                              input_errors=5, output_errors=2),
        ]

    解析策略：
        - 用 regex 匹配 "介面名  數字  數字" 格式（至少 3 欄位）
        - 第一個數字 → input_errors，第二個數字 → output_errors
        - crc_errors 固定為 0（此簡化 parser 不區分 CRC vs 其他 input error）

    已知邊界情況：
        - 不同 IOS 版本的 show interfaces counters errors 欄位數量不同
          （有些有 6+ 欄位，有些只有 2 欄位）
        - 此 parser 目前只取前兩個數字欄位
        - 表頭行（含 "Interface", "Port" 等文字）不會被 regex 匹配到
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "error_count"
    command = "show interfaces counters errors"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        """
        Parse 'show interfaces counters errors' output.

        Example:
        Interface            Input(errs)       Output(errs)
        Gi1/0/1                        0                  0
        Gi1/0/2                        5                  2
        """
        results = []

        pattern = re.compile(
            r"^([A-Za-z0-9\/]+)\s+(\d+)\s+(\d+)",
            re.MULTILINE,
        )

        for line in raw_output.strip().splitlines():
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue

            results.append(
                InterfaceErrorData(
                    interface_name=match.group(1),
                    crc_errors=0,
                    input_errors=int(match.group(2)),
                    output_errors=int(match.group(3)),
                )
            )

        return results


parser_registry.register(CiscoIosErrorParser())
