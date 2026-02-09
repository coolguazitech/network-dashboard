"""
Cisco IOS Version Parser — 解析 Cisco IOS 韌體版本資訊。

CLI 指令：show version
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "version"

輸出模型：list[VersionData]（通常只有一筆）
    VersionData 欄位：
        version: str           — IOS 版本號（如 "17.9.4", "15.0(2)SE11"）
        model: str | None      — 設備型號行（如 "Cisco Catalyst C9200L-48P-4G Switch"）
        serial_number: str|None — 序號（此 parser 不解析此欄位，為 None）
        uptime: str | None     — 運行時間（此 parser 不解析此欄位，為 None）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class CiscoIosVersionParser(BaseParser[VersionData]):
    """
    Cisco IOS 韌體版本 Parser。

    CLI 指令：show version

    輸入格式（raw_output 範例）：
    ::

        Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4, RELEASE SOFTWARE (fc2)
        Technical Support: http://www.cisco.com/techsupport
        Copyright (c) 1986-2024 by Cisco Systems, Inc.
        Compiled Mon 01-Apr-24 12:00 by mcpre

        Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE11, RELEASE SOFTWARE (fc3)
        ...
        cisco WS-C3750X-48 (PowerPC405) processor (revision G0) with 262144K bytes of memory.
        ...
        Cisco Catalyst C9200L-48P-4G Switch

    輸出格式（parse() 回傳值）：
    ::

        [
            VersionData(version="17.9.4", model="Cisco Catalyst C9200L-48P-4G Switch"),
        ]

    解析策略：
        1. 匹配 "Version X.Y.Z" → 取第一個匹配到的版本號
        2. 匹配包含 "Switch" 或 "Chassis" 的行（排除 "Copyright"）→ 取為 model
        3. 若完全找不到 version → 回傳空列表 []

    已知邊界情況：
        - IOS 版本號格式多樣："17.9.4", "15.0(2)SE11", "16.12.3a"
          regex 會匹配 "Version" 後面的整個版本字串（包含字母後綴）
        - IOS-XE 的 show version 輸出更長，但版本行格式相同
        - model 行可能是 "Cisco Catalyst C9200L..." 或 "cisco WS-C3750X..."
          只要包含 "Switch" 或 "Chassis" 就會被匹配
        - serial_number 在 show version 中可找到但此 parser 未實作
        - 找不到版本 → 回傳空列表 []（不是 error）
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "version"
    command = "show version"

    def parse(self, raw_output: str) -> list[VersionData]:
        """
        Parse 'show version' output.

        Example:
        Cisco IOS Software, Version 17.9.4
        Copyright (c) 1986-2024 by Cisco Systems, Inc.
        Cisco Catalyst C9200L-48P-4G Switch
        """
        version = None
        model = None

        for line in raw_output.strip().splitlines():
            line = line.strip()

            # Match "Version X.Y.Z" pattern
            ver_match = re.search(r"Version\s+([\d.]+\w*)", line)
            if ver_match and version is None:
                version = ver_match.group(1)
                continue

            # Match model line containing "Switch" or "Chassis"
            if ("Switch" in line or "Chassis" in line) and not line.startswith("Copyright"):
                model = line
                continue

        if version:
            return [VersionData(version=version, model=model)]

        return []


parser_registry.register(CiscoIosVersionParser())
