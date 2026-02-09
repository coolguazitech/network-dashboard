"""
Cisco IOS Port-Channel (EtherChannel) Parser — 解析 Cisco IOS EtherChannel 狀態。

CLI 指令：show etherchannel summary
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "port_channel"

輸出模型：list[PortChannelData]
    PortChannelData 欄位：
        interface_name: str              — Port-Channel 名稱（如 "Po1"）
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


class CiscoIosPortChannelParser(BaseParser[PortChannelData]):
    """
    Cisco IOS Port-Channel (EtherChannel) Parser。

    CLI 指令：show etherchannel summary

    輸入格式（raw_output 範例）：
    ::

        Flags:  D - down        P - bundled in port-channel
                I - stand-alone s - suspended
                H - Hot-standby (LACP only)
                R - Layer3      S - Layer2
                U - in use      f - failed to allocate aggregator

                u - unsuitable for bundling
                w - waiting to be aggregated
                d - default port

        Number of channel-groups in use: 2
        Number of aggregators:           2

        Group  Port-channel  Protocol    Ports
        ------+-------------+-----------+-----------------------------------------------
        1      Po1(SU)       LACP        Gi1/0/25(P)    Gi1/0/26(P)
        2      Po2(SD)       LACP        Gi1/0/27(D)    Gi1/0/28(D)
        3      Po3(SU)       -           Gi1/0/29(P)    Gi1/0/30(P)

    輸出格式（parse() 回傳值）：
    ::

        [
            PortChannelData(
                interface_name="Po1", status="up", protocol="lacp",
                members=["Gi1/0/25", "Gi1/0/26"],
                member_status={"Gi1/0/25": "up", "Gi1/0/26": "up"}),
            PortChannelData(
                interface_name="Po2", status="down", protocol="lacp",
                members=["Gi1/0/27", "Gi1/0/28"],
                member_status={"Gi1/0/27": "down", "Gi1/0/28": "down"}),
            PortChannelData(
                interface_name="Po3", status="up", protocol=None,
                members=["Gi1/0/29", "Gi1/0/30"],
                member_status={"Gi1/0/29": "up", "Gi1/0/30": "up"}),
        ]

    IOS EtherChannel 狀態碼對照：
        Port-Channel 狀態碼（括號內）：
            S = Layer2, U = in use → SU 表示 UP
            S = Layer2, D = down  → SD 表示 DOWN

        成員狀態碼（括號內）：
            P = bundled (Port is in port-channel) → UP
            D = down → DOWN
            s = suspended, H = hot-standby, I = stand-alone → 非正常

    解析策略：
        - 跳過表頭（"Group", "---" 開頭的行）
        - 用 regex 匹配 "Group  PoN(XX)  Protocol  Members..." 格式
        - Port-Channel 名稱和狀態從 "Po1(SU)" 中解析
        - Protocol 為 "-" 時表示 static（設為 None）

    已知邊界情況：
        - Protocol 為 "-" 的是 static EtherChannel（非 LACP/PAgP）→ protocol=None
        - status 和 member_status 由 PortChannelData 的 Pydantic validator 自動正規化
        - 某些行可能有多個成員跨行顯示（此 parser 假設成員在同一行）
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "port_channel"
    command = "show etherchannel summary"

    def parse(self, raw_output: str) -> list[PortChannelData]:
        """
        Parse 'show etherchannel summary' output.

        Example:
        Group  Port-channel  Protocol    Ports
        ------+-------------+-----------+-------
        1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
        """
        results = []

        # Match: Group  Po1(SU)  Protocol  Members...
        pattern = re.compile(
            r"^(\d+)\s+(\S+)\s+(\S+)\s+(.*)$",
            re.MULTILINE,
        )

        for line in raw_output.strip().splitlines():
            line = line.strip()
            # Skip headers and separators
            if not line or line.startswith("Group") or line.startswith("---"):
                continue

            match = pattern.match(line)
            if not match:
                continue

            pc_name_status = match.group(2)
            protocol = match.group(3)
            members_str = match.group(4)

            # Parse Po name and status: Po1(SU) -> Po1, SU
            pc_match = re.match(r"([^(]+)\(([^)]+)\)", pc_name_status)
            if pc_match:
                pc_name = pc_match.group(1)
                pc_status_code = pc_match.group(2)
                pc_status = "UP" if "U" in pc_status_code else "DOWN"
            else:
                pc_name = pc_name_status
                pc_status = "UNKNOWN"

            # Parse members: Gi1/0/25(P) Gi1/0/26(P)
            members = []
            member_status = {}

            for token in members_str.split():
                m_match = re.match(r"([^(]+)\(([^)]+)\)", token)
                if m_match:
                    m_name = m_match.group(1)
                    m_code = m_match.group(2)
                    members.append(m_name)
                    # P = bundled (Up), D = Down
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
                    member_status=member_status,
                )
            )

        return results


parser_registry.register(CiscoIosPortChannelParser())
