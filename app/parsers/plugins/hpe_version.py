"""
HPE Comware Version Parser — 解析 HPE Comware 韌體版本資訊。

CLI 指令：display version
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "version"

輸出模型：list[VersionData]（通常只有一筆）
    VersionData 欄位：
        version: str           — 韌體版本號（如 "6635P07"）
        model: str | None      — 設備型號（如 "HPE FF 5710 48SFP+ 6QS 2SL Switch"）
        serial_number: str|None — 序號（此 parser 不解析此欄位，為 None）
        uptime: str | None     — 運行時間（此 parser 不解析此欄位，為 None）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class HpeVersionParser(BaseParser[VersionData]):
    """
    HPE Comware 韌體版本 Parser。

    CLI 指令：display version

    輸入格式（raw_output 範例）：
    ::

        HPE Comware Platform Software
        Comware Software, Version 7.1.070, Release 6635P07
        Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
        HPE FF 5710 48SFP+ 6QS 2SL Switch uptime is 0 weeks, 3 days, 5 hours, 22 minutes
        Last reboot reason : User reboot

        Slot 1:
        Uptime is 0 weeks,3 days,5 hours,22 minutes
        HPE FF 5710 48SFP+ 6QS 2SL Switch with 1 Processor
        ...

    輸出格式（parse() 回傳值）：
    ::

        [
            VersionData(version="6635P07", model="HPE FF 5710 48SFP+ 6QS 2SL Switch"),
        ]

    解析策略：
        1. 優先匹配 "Release XXXXX" → 取 Release 號作為 version
        2. 匹配 "HPE ... Switch" → 取為 model
        3. 若沒找到 Release，退而求其次匹配 "Version X.Y.Z"
        4. 若完全找不到 version → 回傳空列表 []

    已知邊界情況：
        - Release 號碼格式不固定（如 "6635P07", "3507P02"）
        - model 行必須以 "HPE" 開頭且包含 "Switch"
        - serial_number 和 uptime 不在此指令中解析（HPE 需要 display device manuinfo）
        - 找不到任何版本資訊 → 回傳空列表 []（不是 error）
    """

    device_type = DeviceType.HPE
    indicator_type = "version"
    command = "display version"

    def parse(self, raw_output: str) -> list[VersionData]:
        """
        Parse 'display version' output.

        Example:
        HPE Comware Platform Software
        Comware Software, Version 7.1.070, Release 6635P07
        Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
        HPE FF 5710 48SFP+ 6QS 2SL Switch
        """
        version = None
        model = None

        for line in raw_output.strip().splitlines():
            line = line.strip()

            # Match Release version: "Release 6635P07"
            release_match = re.search(r"Release\s+(\S+)", line)
            if release_match:
                version = release_match.group(1)
                continue

            # Match model line: "HPE FF 5710 ..."
            if line.startswith("HPE") and "Switch" in line:
                model = line
                continue

        if not version:
            # Fallback: try Comware Software Version
            for line in raw_output.strip().splitlines():
                ver_match = re.search(
                    r"Version\s+([\d.]+)", line
                )
                if ver_match:
                    version = ver_match.group(1)
                    break

        if version:
            return [
                VersionData(
                    version=version,
                    model=model,
                )
            ]

        return []


# Register parser
parser_registry.register(HpeVersionParser())
