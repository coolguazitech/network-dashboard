"""
HPE Comware Fan Status Parser — 解析 HPE Comware 風扇狀態資料。

CLI 指令：display fan
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "fan"

輸出模型：list[FanStatusData]
    FanStatusData 欄位：
        fan_id: str              — 風扇 ID（如 "1", "2"）
        status: str              — 自動正規化為 OperationalStatus 枚舉值
                                   "Normal" → "normal", "Absent" → "absent"
        speed_rpm: int | None    — 轉速 (RPM)，HPE 通常不提供，為 None
        speed_percent: int | None — 轉速百分比，HPE 通常不提供，為 None
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class HpeFanParser(BaseParser[FanStatusData]):
    """
    HPE Comware 風扇狀態 Parser。

    CLI 指令：display fan

    輸入格式（raw_output 範例）：
    ::

         Slot 1:
         FanID    Status      Direction
         1        Normal      Back-to-front
         2        Normal      Back-to-front
         3        Absent      --

    輸出格式（parse() 回傳值）：
    ::

        [
            FanStatusData(fan_id="1", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="2", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="3", status="absent", speed_rpm=None, speed_percent=None),
        ]

    解析策略：
        - 跳過 "Slot" 和 "FanID" 開頭的表頭行
        - 用 regex 匹配 "數字  狀態  方向" 格式的資料行
        - status 由 FanStatusData 的 Pydantic validator 自動正規化

    已知邊界情況：
        - HPE Comware 不提供 RPM / 百分比轉速 → speed_rpm, speed_percent 均為 None
        - "Absent" 表示風扇不存在（空槽位），仍會回傳一筆資料
        - 多 Slot 設備：每個 Slot 會有一組 "Slot N:" 標題，但 FanID 可能重複
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "fan"
    command = "display fan"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        """
        Parse 'display fan' output.
        
        Example:
         Slot 1:
         FanID    Status      Direction
         1        Normal      Back-to-front
        """
        results = []
        
        # Regex to capture fan line
        # Group 1: Fan ID
        # Group 2: Status
        # Group 3: Direction (optional)
        pattern = re.compile(
            r"^\s*(\d+)\s+(\S+)\s+(.+?)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            # Skip headers
            if line.startswith("Slot") or line.startswith("FanID"):
                continue
                
            match = pattern.match(line)
            if not match:
                continue
                
            fan_id = match.group(1)
            status = match.group(2)
            
            results.append(
                FanStatusData(
                    fan_id=fan_id,
                    status=status,
                    speed_rpm=None,
                    speed_percent=None
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpeFanParser())
