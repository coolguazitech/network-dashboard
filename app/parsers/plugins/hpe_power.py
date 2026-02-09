"""
HPE Comware Power Supply Parser — 解析 HPE Comware 電源供應器狀態。

CLI 指令：display power
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "power"

輸出模型：list[PowerData]
    PowerData 欄位：
        ps_id: str                    — 電源 ID（如 "1", "2"）
        status: str                   — 自動正規化為 OperationalStatus 枚舉值
        input_status: str | None      — 輸入狀態（HPE 設為與 status 相同）
        output_status: str | None     — 輸出狀態（HPE 設為與 status 相同）
        capacity_watts: float | None  — 額定瓦數，HPE 格式通常不提供，為 None
        actual_output_watts: float | None — 實際輸出瓦數
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class HpePowerParser(BaseParser[PowerData]):
    """
    HPE Comware 電源供應器 Parser。

    CLI 指令：display power

    輸入格式（raw_output 範例）：
    ::

         Slot 1:
         PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
         1       Normal   AC     --          --          --        Back-to-front
         2       Normal   AC     2.1         220         462       Back-to-front

    輸出格式（parse() 回傳值）：
    ::

        [
            PowerData(ps_id="1", status="normal", capacity_watts=None,
                      actual_output_watts=None, input_status="normal",
                      output_status="normal"),
            PowerData(ps_id="2", status="normal", capacity_watts=None,
                      actual_output_watts=462.0, input_status="normal",
                      output_status="normal"),
        ]

    解析策略：
        - 用 regex 匹配 "ID  State  Mode  Current  Voltage  Power  FanDir" 表格行
        - Power(W) 欄位的 "--" 會解析為 None
        - capacity_watts（額定瓦數）在 HPE 輸出中通常不可得，固定為 None
        - input_status / output_status 設為與 State 欄位相同

    已知邊界情況：
        - 數值欄位為 "--" 時會解析為 None
        - 多 Slot 設備可能有多組 "Slot N:" 區塊
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "power"
    command = "display power"

    def parse(self, raw_output: str) -> list[PowerData]:
        """
        Parse 'display power' output.
        
        Example:
         Slot 1:
         PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
         1       Normal   AC     --          --          --        Back-to-front
         2       Normal   AC     --          --          --        Back-to-front
        """
        results = []
        
        # Regex for table rows
        # 1       Normal   AC     --          --          --        Back-to-front
        # Group 1: ID
        # Group 2: State
        # Group 3: Mode
        # Group 4: Current
        # Group 5: Voltage
        # Group 6: Power
        pattern = re.compile(
            r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            match = pattern.match(line)
            if not match:
                continue
                
            ps_id = match.group(1)
            state = match.group(2)
            
            # Helper to parse float or None
            def parse_float(val: str) -> float | None:
                if val == "--" or not val:
                    return None
                try:
                    return float(val)
                except ValueError:
                    return None
            
            actual_power = parse_float(match.group(6))
            
            results.append(
                PowerData(
                    ps_id=ps_id,
                    status=state,
                    capacity_watts=None,  # HPE output often doesn't show total capacity here
                    actual_output_watts=actual_power,
                    input_status=state,
                    output_status=state
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpePowerParser())
