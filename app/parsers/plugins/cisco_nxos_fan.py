"""
Cisco NX-OS Fan Status Parser — 解析 Cisco NX-OS 風扇狀態資料。

CLI 指令：show environment fan
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "fan"

輸出模型：list[FanStatusData]
    FanStatusData 欄位：
        fan_id: str              — 風扇 ID（如 "Fan1(Sys_Fan1)"）
        status: str              — 自動正規化為 OperationalStatus 枚舉值
                                   "Ok" → "ok", "Absent" → "absent"
        speed_rpm: int | None    — 轉速 (RPM)，此指令不提供，為 None
        speed_percent: int | None — 轉速百分比，此指令不提供，為 None

注意：
    NX-OS 的 fan 指令與 IOS 不同：
    - NX-OS：show environment fan（專用指令，表格格式）
    - IOS：show environment（混合指令，含 fan + power + temp）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData
from app.parsers.registry import parser_registry


class CiscoNxosFanParser(BaseParser[FanStatusData]):
    """
    Cisco NX-OS 風扇狀態 Parser。

    CLI 指令：show environment fan
    測試設備：Nexus 9000, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        Fan             Model                Hw     Direction  Status
        --------------------------------------------------------------
        Fan1(Sys_Fan1)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan2(Sys_Fan2)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan3(Sys_Fan3)  NXA-FAN-30CFM-F      --     front-to-back  Absent
        Fan4(Sys_Fan4)  NXA-FAN-30CFM-F      --     front-to-back  Ok
        Fan_in_PS1      --                   --     front-to-back  Ok
        Fan_in_PS2      --                   --     front-to-back  Ok

    輸出格式（parse() 回傳值）：
    ::

        [
            FanStatusData(fan_id="Fan1(Sys_Fan1)", status="ok",
                         speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="Fan2(Sys_Fan2)", status="ok",
                         speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="Fan3(Sys_Fan3)", status="absent",
                         speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="Fan4(Sys_Fan4)", status="ok",
                         speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="Fan_in_PS1", status="ok",
                         speed_rpm=None, speed_percent=None),
            FanStatusData(fan_id="Fan_in_PS2", status="ok",
                         speed_rpm=None, speed_percent=None),
        ]

    解析策略：
        - 跳過表頭行（"Fan " 開頭，注意有空格）和 "---" 分隔線
        - 用 regex 匹配 "FanXXX  Model  Hw  Status" 格式
        - fan_id 取整個名稱（如 "Fan1(Sys_Fan1)"），包含括號
        - status 取最後一個欄位（最右邊的 column）

    已知邊界情況（重要！）：
        - NX-OS 的表格欄位數可能因版本/型號而異
          有些版本有 Direction 欄位，有些沒有
          regex 設計為取「第一個欄位」和「最後一個欄位」
        - "Absent" 表示風扇不存在（空槽位），仍會回傳一筆資料
        - "Fan " 開頭（含空格）是表頭；"Fan1..." 開頭（無空格後接數字）是資料
          → 跳過邏輯用 line.startswith("Fan ") 區分
        - CORE 設備（Cisco-NXOS）的風扇格式與 ACCESS 設備可能不同
          → 這曾經是一個 bug 的來源（見 MEMORY.md: Fan parser bug）
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "fan"
    command = "show environment fan"

    def parse(self, raw_output: str) -> list[FanStatusData]:
        results = []

        # 匹配: Fan1(Sys_Fan1)  NXA-FAN-30CFM-F  --  Ok
        # group(1) = "Fan1(Sys_Fan1)", group(2) = "Ok"
        pattern = re.compile(
            r"^(Fan\S+)\s+\S+\s+\S+\s+(\S+)\s*$",
        )

        for line in raw_output.strip().splitlines():
            line = line.strip()
            # 跳過 header 和分隔線
            if not line or line.startswith("---") or line.startswith("Fan "):
                continue

            match = pattern.match(line)
            if not match:
                continue

            results.append(
                FanStatusData(
                    fan_id=match.group(1),
                    status=match.group(2),
                    speed_rpm=None,
                    speed_percent=None,
                )
            )

        return results


parser_registry.register(CiscoNxosFanParser())
