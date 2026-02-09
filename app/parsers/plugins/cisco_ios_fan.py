"""
Cisco IOS Fan Status Parser — 解析 Cisco IOS 風扇狀態資料。

CLI 指令：show environment
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "fan"

輸出模型：list[FanStatusData]
    FanStatusData 欄位：
        fan_id: str              — 風扇 ID（如 "1", "2"）
        status: str              — 自動正規化為 OperationalStatus 枚舉值
                                   "OK" → "normal"(由 parser 手動轉), "NOT OK" → "fail"
        speed_rpm: int | None    — 轉速 (RPM)，IOS 不提供，為 None
        speed_percent: int | None — 轉速百分比，IOS 不提供，為 None

注意：
    IOS 的 show environment 輸出包含 fan 和 power 資訊混在一起。
    此 parser 只抓取 "FAN N is ..." 格式的行。
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class CiscoIosFanParser(BaseParser[FanStatusData]):
    """
    Cisco IOS 風扇狀態 Parser。

    CLI 指令：show environment
    測試設備：Catalyst 3750, 2960, 9200 系列

    輸入格式（raw_output 範例）：
    ::

        FAN 1 is OK
        FAN 2 is OK
        FAN 3 is NOT OK
        FAN 4 is OK

        FAN PS-1 is OK
        FAN PS-2 is NOT PRESENT

    輸出格式（parse() 回傳值）：
    ::

        [
            FanStatusData(fan_id="1", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="2", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="3", status="fail",   speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="4", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="PS-1", status="normal", speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="PS-2", status="fail",   speed_rpm=None, speed_percent=None),
        ]

    解析策略：
        - 用 regex 匹配 "FAN XXX is YYY" 格式
        - "OK" → status="normal"
        - 其他任何值（"NOT OK", "NOT PRESENT" 等）→ status="fail"
        - status 進入 FanStatusData 後會被 Pydantic validator 正規化

    已知邊界情況：
        - IOS 的 show environment 輸出同時包含 fan、power、temperature 區段
          此 parser 只匹配 "FAN" 開頭的行，其餘忽略
        - fan_id 可能是數字（"1"）或帶前綴（"PS-1", "PS-2"）
        - 沒有 RPM / 百分比資訊 → speed_rpm, speed_percent 均為 None
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "fan"
    command = "show environment"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results = []

        # 匹配: FAN 1 is OK / FAN 3 is NOT OK
        # group(1) = fan number, group(2) = status text after "is "
        pattern = re.compile(
            r"^FAN\s+(\S+)\s+is\s+(.+)$",
            re.IGNORECASE,
        )

        for line in raw_output.strip().splitlines():
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue

            fan_id = match.group(1)
            raw_status = match.group(2).strip()

            # "OK" → normal, "NOT OK" → fail
            if raw_status.upper() == "OK":
                status = "normal"
            else:
                status = "fail"

            results.append(
                FanStatusData(
                    fan_id=fan_id,
                    status=status,
                    speed_rpm=None,
                    speed_percent=None,
                )
            )

        return results


parser_registry.register(CiscoIosFanParser())
