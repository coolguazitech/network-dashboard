"""
HPE Comware Interface Error Parser — 解析 HPE Comware 介面錯誤計數器。

CLI 指令：display counters error
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "error_count"

輸出模型：list[InterfaceErrorData]
    InterfaceErrorData 欄位：
        interface_name: str    — 介面名稱（如 "GE1/0/1"）
        crc_errors: int        — CRC 錯誤計數（HPE 簡化格式固定為 0）
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


class HpeErrorParser(BaseParser[InterfaceErrorData]):
    """
    HPE Comware 介面錯誤計數器 Parser。

    CLI 指令：display counters error

    輸入格式（raw_output 範例）：
    ::

        Interface            Input(errs)       Output(errs)
        GE1/0/1                        0                  0
        GE1/0/2                       12                  3
        GE1/0/3                        0                  0
        XGE1/0/25                      0                  0

    輸出格式（parse() 回傳值）：
    ::

        [
            InterfaceErrorData(interface_name="GE1/0/1", crc_errors=0,
                              input_errors=0, output_errors=0),
            InterfaceErrorData(interface_name="GE1/0/2", crc_errors=0,
                              input_errors=12, output_errors=3),
            InterfaceErrorData(interface_name="GE1/0/3", crc_errors=0,
                              input_errors=0, output_errors=0),
            InterfaceErrorData(interface_name="XGE1/0/25", crc_errors=0,
                              input_errors=0, output_errors=0),
        ]

    解析策略：
        - 用 regex 匹配 "介面名  數字  數字" 格式的行
        - 表頭行（包含 "Interface" 等文字）不會被 regex 匹配到

    已知邊界情況：
        - HPE Comware 的 display counters error 只提供 Input/Output 兩個欄位
          → crc_errors 固定為 0（HPE 未在此指令中細分 CRC）
        - collisions, giants, runts 也因格式限制預設為 0
        - 若需要更詳細的錯誤計數，需要用 display interface 逐介面查詢
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "error_count"
    command = "display counters error"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        """
        Parse 'display counters error' output.
        
        Example:
        Interface            Input(errs)       Output(errs)
        GE1/0/1                        0                  0
        GE1/0/2                        0                  0
        """
        results = []
        
        # Regex to capture error line
        # Group 1: Interface
        # Group 2: Input errors
        # Group 3: Output errors
        pattern = re.compile(
            r"^([A-Za-z0-9\/]+)\s+(\d+)\s+(\d+)",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface = match.group(1)
            input_err = int(match.group(2))
            output_err = int(match.group(3))
            
            results.append(
                InterfaceErrorData(
                    interface_name=interface,
                    crc_errors=0, # HPE output might be simplified here
                    input_errors=input_err,
                    output_errors=output_err,
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpeErrorParser())
