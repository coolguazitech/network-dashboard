"""
Cisco IOS Neighbor (CDP) Parser Plugin — 解析 Cisco IOS CDP 鄰居資訊。

CLI 指令：show cdp neighbors detail
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "uplink"    ← 注意是 "uplink" 不是 "neighbor" 或 "cdp"！

輸出模型：list[NeighborData]
    NeighborData 欄位：
        local_interface: str      — 本地介面名稱（如 "GigabitEthernet1/0/1"）
        remote_hostname: str      — 遠端設備名稱（Device ID）
        remote_interface: str     — 遠端介面名稱（Port ID outgoing port）
        remote_platform: str|None — 遠端平台描述（Platform 欄位）

重要提醒：
    - Cisco IOS 使用 CDP（Cisco Discovery Protocol），不是 LLDP
    - indicator_type 是 "uplink"，與 HPE 的 LLDP parser 保持一致
    - MockFetcher 必須產生 CDP 格式的輸出才能被此 parser 正確解析
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class CiscoIosNeighborParser(BaseParser[NeighborData]):
    """
    Cisco IOS CDP 鄰居 Parser。

    CLI 指令：show cdp neighbors detail
    測試設備：Catalyst 3750, 2960 系列

    輸入格式（raw_output 範例）：
    ::

        -------------------------
        Device ID: Router01
        Entry address(es):
          IP address: 10.1.1.1
        Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24
        Holdtime : 179 sec

        Version :
        Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE11

        advertisement version: 2
        VTP Management Domain: 'DOMAIN01'
        Native VLAN: 1
        Duplex: full
        Management address(es):
          IP address: 10.1.1.1

        -------------------------
        Device ID: Switch02.domain.com
        Platform: cisco WS-C2960X-48FPS-L,  Capabilities: Switch IGMP
        Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet0/1
        ...

    輸出格式（parse() 回傳值）：
    ::

        [
            NeighborData(local_interface="GigabitEthernet1/0/1",
                        remote_hostname="Router01",
                        remote_interface="GigabitEthernet1/0/24",
                        remote_platform="cisco WS-C3750X-48"),
            NeighborData(local_interface="GigabitEthernet1/0/2",
                        remote_hostname="Switch02.domain.com",
                        remote_interface="GigabitEthernet0/1",
                        remote_platform="cisco WS-C2960X-48FPS-L"),
        ]

    解析策略：
        - 以 "----" 分隔線分割鄰居區塊
        - 在每個區塊中提取：
          - "Device ID: XXX" → remote_hostname
          - "Platform: XXX, Capabilities:" → remote_platform
          - "Interface: XXX, Port ID (outgoing port): YYY"
            → local_interface=XXX, remote_interface=YYY
        - 需要三個必填欄位都存在才會產生 NeighborData

    已知邊界情況：
        - Device ID 可能帶 domain（"Switch02.domain.com"），取完整字串
        - 最後一個鄰居區塊後面可能沒有 "----" 分隔線，需特別處理
        - 若 CDP 未啟用或沒有鄰居 → 回傳空列表 []
        - Platform 行的格式是 "Platform: XXX,  Capabilities: YYY"
          逗號前是平台，逗號後是能力，只取平台部分
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "uplink"
    command = "show cdp neighbors detail"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse Cisco IOS CDP neighbor output.

        Example output format:
        -------------------------
        Device ID: Router01
        Entry address(es):
          IP address: 10.1.1.1
        Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP
        Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24
        Holdtime : 179 sec

        Version :
        Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE11

        advertisement version: 2
        Protocol Hello:  OUI=0x00000C, Protocol ID=0x0112; payload len=27, value=00000000FFFFFFFF010221FF0000000000000000000000
        VTP Management Domain: 'DOMAIN01'
        Native VLAN: 1
        Duplex: full
        Management address(es):
          IP address: 10.1.1.1

        -------------------------
        Device ID: Switch02
        ...

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[NeighborData]: Parsed neighbor data
        """
        results: list[NeighborData] = []
        current_data: dict[str, str] = {}

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Separator line indicates start of new neighbor or end of previous
            if line.startswith("----"):
                # Save previous neighbor if complete
                if current_data and all(
                    k in current_data
                    for k in ["local_interface", "remote_hostname", "remote_interface"]
                ):
                    results.append(
                        NeighborData(
                            local_interface=current_data["local_interface"],
                            remote_hostname=current_data["remote_hostname"],
                            remote_interface=current_data["remote_interface"],
                            remote_platform=current_data.get("remote_platform"),
                        )
                    )
                    current_data = {}
                continue

            # Skip empty lines
            if not line:
                continue

            # Parse Device ID (remote hostname)
            # e.g., "Device ID: Router01"
            device_id_match = re.search(
                r"Device\s+ID:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if device_id_match:
                current_data["remote_hostname"] = device_id_match.group(1)
                continue

            # Parse Platform (for platform info)
            # e.g., "Platform: cisco WS-C3750X-48,  Capabilities: Router Switch IGMP"
            platform_match = re.search(
                r"Platform:\s*(.+?),\s*Capabilities:",
                line,
                re.IGNORECASE,
            )
            if platform_match:
                current_data["remote_platform"] = platform_match.group(1).strip()
                continue

            # Parse Interface and Port ID
            # e.g., "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24"
            interface_match = re.search(
                r"Interface:\s*([^,]+),\s*Port\s+ID\s*\(outgoing\s+port\):\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if interface_match:
                current_data["local_interface"] = interface_match.group(1).strip()
                current_data["remote_interface"] = interface_match.group(2).strip()
                continue

        # Don't forget the last neighbor entry
        if current_data and all(
            k in current_data
            for k in ["local_interface", "remote_hostname", "remote_interface"]
        ):
            results.append(
                NeighborData(
                    local_interface=current_data["local_interface"],
                    remote_hostname=current_data["remote_hostname"],
                    remote_interface=current_data["remote_interface"],
                    remote_platform=current_data.get("remote_platform"),
                )
            )

        return results


# Register the parser
parser_registry.register(CiscoIosNeighborParser())
