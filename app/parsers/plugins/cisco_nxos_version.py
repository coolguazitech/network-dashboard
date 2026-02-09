"""
Cisco NX-OS Version Parser — 解析 Cisco NX-OS 韌體版本資訊。

CLI 指令：show version
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "version"

輸出模型：list[VersionData]（通常只有一筆）
    VersionData 欄位：
        version: str           — NX-OS 版本號（如 "10.3.3", "9.3(12)"）
        model: str | None      — 設備型號行（如 "cisco Nexus9000 C9336C-FX2 Chassis"）
        serial_number: str|None — 序號（此 parser 不解析此欄位，為 None）
        uptime: str | None     — 運行時間（此 parser 不解析此欄位，為 None）

NX-OS vs IOS 差異：
    - NX-OS 的版本行格式是 "NXOS: version X.Y.Z"（有 "NXOS:" 前綴）
    - IOS 的版本行格式是 "Version X.Y.Z"（無前綴）
    - NX-OS 的設備型號包含 "Chassis"；IOS 包含 "Switch"
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, VersionData
from app.parsers.registry import parser_registry


class CiscoNxosVersionParser(BaseParser[VersionData]):
    """
    Cisco NX-OS 韌體版本 Parser。

    CLI 指令：show version

    輸入格式（raw_output 範例）：
    ::

        Cisco Nexus Operating System (NX-OS) Software
        TAC support: http://www.cisco.com/tac
        Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html
        Copyright (c) 2002-2024, Cisco Systems, Inc. All rights reserved.
        The copyrights to certain works contained herein are owned by
        other third parties and are used and distributed under license.
        Some parts of this software are covered under the GNU Public
        License. A copy of the license is available at
        http://www.gnu.org/licenses/gpl.html.

        NXOS: version 10.3.3
        NXOS image file is: bootflash:///nxos64-cs.10.3.3.F.bin
        NXOS compile time:  3/25/2024 22:00:00 [03/26/2024 06:25:09]

        Hardware
          cisco Nexus9000 C9336C-FX2 Chassis
          Intel(R) Xeon(R) CPU D-1526 @ 1.80GHz with 24632060 kB of memory.
          Processor Board ID FDO12345678

    輸出格式（parse() 回傳值）：
    ::

        [
            VersionData(version="10.3.3",
                       model="cisco Nexus9000 C9336C-FX2 Chassis"),
        ]

    解析策略：
        1. 優先匹配 NX-OS 專用格式 "NXOS: version X.Y.Z"
        2. 若沒找到，退而求其次匹配通用 "Version X.Y.Z"
        3. 匹配包含 "Chassis" 或 "Switch" 的行（排除 "Copyright"）→ 取為 model
        4. 若完全找不到 version → 回傳空列表 []

    已知邊界情況：
        - NX-OS 版本號格式："10.3.3", "9.3(12)", "10.2.5.F"
          regex 會匹配版本號開頭的數字和點（可能含字母後綴）
        - model 行在 "Hardware" 段落下方，通常以 "cisco" 開頭（小寫 c）
        - serial_number 在 "Processor Board ID" 行中，但此 parser 未實作
        - 找不到版本 → 回傳空列表 []（不是 error）
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "version"
    command = "show version"

    def parse(self, raw_output: str) -> list[VersionData]:
        """
        Parse 'show version' output.

        Example:
        Cisco Nexus Operating System (NX-OS) Software
        NXOS: version 10.3.3
        Hardware
          cisco Nexus9000 C9336C-FX2 Chassis
        """
        version = None
        model = None

        for line in raw_output.strip().splitlines():
            line = line.strip()

            # NXOS-specific: "NXOS: version X.Y.Z"
            nxos_match = re.search(r"NXOS:\s*version\s+([\d.]+\w*)", line, re.IGNORECASE)
            if nxos_match:
                version = nxos_match.group(1)
                continue

            # Fallback: "Version X.Y.Z"
            if version is None:
                ver_match = re.search(r"Version\s+([\d.]+\w*)", line)
                if ver_match:
                    version = ver_match.group(1)
                    continue

            # Match model line containing "Chassis" or "Switch"
            if ("Chassis" in line or "Switch" in line) and not line.startswith("Copyright"):
                model = line
                continue

        if version:
            return [VersionData(version=version, model=model)]

        return []


parser_registry.register(CiscoNxosVersionParser())
