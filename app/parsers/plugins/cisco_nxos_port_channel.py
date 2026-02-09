"""
Cisco NX-OS Port-Channel Parser — 解析 Cisco NX-OS Port-Channel 狀態。

CLI 指令：show port-channel summary
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "port_channel"

輸出模型：list[PortChannelData]
    PortChannelData 欄位：
        interface_name: str              — Port-Channel 名稱（如 "Po1"）
        status: str                      — 自動正規化為 LinkStatus（"up"/"down"/"unknown"）
        protocol: str | None             — 聚合協議，自動正規化為 AggregationProtocol
        members: list[str]               — 成員介面列表（如 ["Eth1/1", "Eth1/2"]）
        member_status: dict[str,str]|None — 各成員的狀態

NX-OS vs IOS 差異：
    - NX-OS 指令是 "show port-channel summary"
    - IOS 指令是 "show etherchannel summary"
    - NX-OS 的表格多一個 Type 欄位
    - 成員介面名用 "Eth" 前綴而非 "Gi"
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PortChannelData
from app.parsers.registry import parser_registry


class CiscoNxosPortChannelParser(BaseParser[PortChannelData]):
    """
    Cisco NX-OS Port-Channel Parser。

    CLI 指令：show port-channel summary
    測試設備：Nexus 9000, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        Flags:  D - Down        P - Up in port-channel (members)
                I - Individual  H - Hot-standby (LACP only)
                s - Suspended   r - Module-removed
                b - BFD Session Wait
                S - Switched    R - Routed
                U - Up (port-channel)
                p - Up in delay-lacp mode (member)
                M - Not in use. Min-links not met
        --------------------------------------------------------------------------------
        Group Port-       Type     Protocol  Member Ports
              Channel
        --------------------------------------------------------------------------------
        1     Po1(SU)     Eth      LACP      Eth1/1(P)    Eth1/2(P)
        10    Po10(SD)    Eth      LACP      Eth1/10(D)   Eth1/11(s)
        20    Po20(SU)    Eth      NONE      Eth1/20(P)

    輸出格式（parse() 回傳值）：
    ::

        [
            PortChannelData(
                interface_name="Po1", status="up", protocol="lacp",
                members=["Eth1/1", "Eth1/2"],
                member_status={"Eth1/1": "up", "Eth1/2": "up"}),
            PortChannelData(
                interface_name="Po10", status="down", protocol="lacp",
                members=["Eth1/10", "Eth1/11"],
                member_status={"Eth1/10": "down", "Eth1/11": "down"}),
            PortChannelData(
                interface_name="Po20", status="up", protocol=None,
                members=["Eth1/20"],
                member_status={"Eth1/20": "up"}),
        ]

    NX-OS Port-Channel 狀態碼對照：
        Port-Channel 狀態碼：
            S = Switched/Routed, U = Up → SU 表示 UP
            S = Switched/Routed, D = Down → SD 表示 DOWN

        成員狀態碼：
            P = Up in port-channel → UP
            D = Down → DOWN
            s = Suspended, I = Individual → 非正常

    解析策略：
        - 用 regex 匹配 "Group  PoN(XX)  Type  Protocol  Members..." 格式
        - 與 IOS 的差別是多了 "Type" 欄位（如 "Eth"）
        - Protocol 為 "-" 或 "NONE" → protocol=None
        - 成員的 (P)/(D)/(s) 狀態碼映射為 UP/DOWN

    已知邊界情況：
        - Protocol "NONE" 表示 static（無動態協議），設為 None
        - status 和 member_status 由 PortChannelData 的 Pydantic validator 自動正規化
        - 某些 NX-OS 版本的 Flags 說明區可能更長（包含 vPC 相關 flag）
        - 成員可能橫跨多行（此 parser 假設成員在同一行）
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "port_channel"
    command = "show port-channel summary"

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse 'show port-channel summary' output.
        
        Example output:
        --------------------------------------------------------------------------------
        Group Port-       Type     Protocol  Member Ports
              Channel
        --------------------------------------------------------------------------------
        1     Po1(SU)     Eth      LACP      Eth1/1(P)    Eth1/2(P)
        10    Po10(SD)    Eth      LACP      Eth1/10(D)
        """
        results = []
        
        # Regex to capture Port-Channel line
        # Group 1: ID
        # Group 2: Name + Status (e.g. Po1(SU))
        # Group 3: Type
        # Group 4: Protocol
        # Group 5: Members string
        pattern = re.compile(
            r"^(\d+)\s+([A-Za-z0-9\(\)]+)\s+(\w+)\s+(\w+|-+)\s+(.*)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            pc_name_status = match.group(2)
            protocol = match.group(4)
            members_str = match.group(5)
            
            # Parse PC Name and Status
            # Po1(SU) -> Po1, SU
            pc_match = re.match(r"([^(]+)\(([^)]+)\)", pc_name_status)
            if pc_match:
                pc_name = pc_match.group(1)
                pc_status_code = pc_match.group(2)
                pc_status = "UP" if "U" in pc_status_code else "DOWN"
            else:
                pc_name = pc_name_status
                pc_status = "UNKNOWN"
                
            # Parse Members
            # Eth1/1(P) Eth1/2(P)
            members = []
            member_status = {}
            
            # Simple split by space, then parse each member
            member_tokens = members_str.split()
            for token in member_tokens:
                m_match = re.match(r"([^(]+)\(([^)]+)\)", token)
                if m_match:
                    m_name = m_match.group(1)
                    m_code = m_match.group(2)
                    members.append(m_name)
                    # P = Up in port-channel, D = Down
                    member_status[m_name] = "UP" if "P" in m_code else "DOWN"
                else:
                    members.append(token)
                    member_status[token] = "UNKNOWN"
            
            results.append(
                PortChannelData(
                    interface_name=pc_name,
                    status=pc_status,
                    protocol=protocol if protocol != "-" else None,
                    members=members,
                    member_status=member_status
                )
            )
            
        return results


# Register the parser
parser_registry.register(CiscoNxosPortChannelParser())
