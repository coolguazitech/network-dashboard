"""
HPE Comware Port-Channel (Bridge-Aggregation) Parser — 解析 HPE Comware 鏈路聚合狀態。

CLI 指令：display link-aggregation verbose（或 summary）
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "port_channel"

輸出模型：list[PortChannelData]
    PortChannelData 欄位：
        interface_name: str              — 聚合介面名稱（如 "BAGG1"）
        status: str                      — 自動正規化為 LinkStatus（"up"/"down"/"unknown"）
        protocol: str | None             — 聚合協議，自動正規化為 AggregationProtocol
                                           ("lacp"/"static"/"pagp"/"none")
        members: list[str]               — 成員介面列表
        member_status: dict[str,str]|None — 各成員的狀態（自動正規化為 LinkStatus）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class HpePortChannelParser(BaseParser[PortChannelData]):
    """
    HPE Comware Port-Channel (Bridge-Aggregation) Parser。

    CLI 指令：display link-aggregation verbose（或 summary）

    輸入格式（raw_output 範例 — summary 格式）：
    ::

        AggID   Interface   Link   Attribute   Mode   Members
        1       BAGG1       UP     A           LACP   GE1/0/1(S) GE1/0/2(S)
        2       BAGG2       DOWN   A           LACP   GE1/0/3(U) GE1/0/4(U)

    輸出格式（parse() 回傳值）：
    ::

        [
            PortChannelData(
                interface_name="BAGG1", status="up", protocol="lacp",
                members=["GE1/0/1", "GE1/0/2"],
                member_status={"GE1/0/1": "up", "GE1/0/2": "up"}),
            PortChannelData(
                interface_name="BAGG2", status="down", protocol="lacp",
                members=["GE1/0/3", "GE1/0/4"],
                member_status={"GE1/0/3": "down", "GE1/0/4": "down"}),
        ]

    解析策略：
        - 此 parser 主要解析 summary 格式（表格形式）
        - 用 regex 匹配 "AggID  Interface  UP/DOWN  Attribute  Mode  Members" 行
        - 成員格式為 "GE1/0/1(S)"，括號內 S=Selected(UP), U=Unselected(DOWN)
        - protocol：若 Mode 包含 "LACP" 或 "Dynamic" → "lacp"，否則 → "static"

    HPE 術語對照：
        - Bridge-Aggregation (BAGG) ≈ Cisco Port-Channel (Po)
        - S (Selected) ≈ P (Bundled) → UP
        - U (Unselected) ≈ D (Down) → DOWN

    已知邊界情況：
        - verbose 格式的輸出結構不同，此 parser 不支援 verbose 格式
        - 成員字串中若沒有括號（極少見），member_status 設為 "UNKNOWN"
        - status 和 member_status 由 PortChannelData 的 Pydantic validator 自動正規化
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "port_channel"
    command = "display link-aggregation verbose"  # or summary

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse 'display link-aggregation summary' output.
        
        Example output:
        Aggregation Interface: Bridge-Aggregation1
        Aggregation Mode: Dynamic
        Loadsharing Type: Shar
        System ID: 0x8000, 3822-d698-0c00
        Local:
          Port             Status  Priority Oper-Key  Flag
        --------------------------------------------------------------------------------
          GE1/0/1          S       32768    1         {ACDEF}
          GE1/0/2          S       32768    1         {ACDEF}
        
        Or summary format:
        AggID   Interface   Link   Attribute   Mode   Members
        1       BAGG1       UP     A           LACP   GE1/0/1(S) GE1/0/2(S)
        """
        results = []
        
        # Strategy: Parse summary format as it's more common for high-level checks
        # Regex for summary line
        # Group 1: AggID
        # Group 2: Interface Name
        # Group 3: Link Status
        # Group 4: Attribute
        # Group 5: Mode
        # Group 6: Members string
        pattern = re.compile(
            r"^(\d+)\s+([A-Za-z0-9_-]+)\s+(UP|DOWN)\s+(\w+)\s+(\w+)\s+(.*)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface_name = match.group(2)
            status = match.group(3)
            mode = match.group(5)
            members_str = match.group(6)
            
            # Protocol inference
            protocol = "LACP" if "LACP" in mode or "Dynamic" in mode else "STATIC"
            
            # Parse Members
            # GE1/0/1(S) GE1/0/2(S)
            members = []
            member_status = {}
            
            member_tokens = members_str.split()
            for token in member_tokens:
                m_match = re.match(r"([^(]+)\(([^)]+)\)", token)
                if m_match:
                    m_name = m_match.group(1)
                    m_code = m_match.group(2)
                    members.append(m_name)
                    # S = Selected (Active/Up), U = Unselected (Standby/Down)
                    member_status[m_name] = "UP" if "S" in m_code else "DOWN"
                else:
                    members.append(token)
                    member_status[token] = "UNKNOWN"
            
            results.append(
                PortChannelData(
                    interface_name=interface_name,
                    status=status,
                    protocol=protocol,
                    members=members,
                    member_status=member_status
                )
            )
            
        return results


# Register parsers
parser_registry.register(HpePortChannelParser())
