"""
HPE Comware Neighbor (LLDP) Parser Plugin — 解析 HPE Comware LLDP 鄰居資訊。

CLI 指令：display lldp neighbor-information
註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "uplink"    ← 注意是 "uplink" 不是 "neighbor"！

輸出模型：list[NeighborData]
    NeighborData 欄位：
        local_interface: str      — 本地介面名稱（如 "GigabitEthernet1/0/1"）
        remote_hostname: str      — 遠端設備名稱（System Name）
        remote_interface: str     — 遠端介面名稱（Port ID）
        remote_platform: str|None — 遠端平台描述（System Description）

重要提醒：
    indicator_type 是 "uplink" 而不是 "neighbor" 或 "lldp"！
    這是因為此 parser 用於 uplink 指標的資料採集。
    Fetcher 的 fetch_type 也必須是 "uplink" 才能配對到此 parser。
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class HpeComwareNeighborParser(BaseParser[NeighborData]):
    """
    HPE Comware LLDP 鄰居 Parser。

    CLI 指令：display lldp neighbor-information
    測試設備：HPE 5130 系列

    輸入格式（raw_output 範例）：
    ::

        LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:
        LLDP neighbor index       : 1
        Chassis type              : MAC address
        Chassis ID                : 0012-3456-789a
        Port ID type              : Interface name
        Port ID                   : GigabitEthernet1/0/24
        Port description          : not advertised
        System name               : Core-Switch-01
        System description        : HPE Comware Platform Software
        System capabilities supported : Bridge, Router
        System capabilities enabled   : Bridge, Router
        Management address type       : IPv4
        Management address            : 10.0.1.1
        Expired time                  : 112s

        LLDP neighbor-information of port 2 [GigabitEthernet1/0/2]:
        LLDP neighbor index       : 1
        Port ID                   : Ethernet1/1
        System name               : Spine-01
        System description        : Cisco Nexus Operating System
        ...

    輸出格式（parse() 回傳值）：
    ::

        [
            NeighborData(local_interface="GigabitEthernet1/0/1",
                        remote_hostname="Core-Switch-01",
                        remote_interface="GigabitEthernet1/0/24",
                        remote_platform="HPE Comware Platform Software"),
            NeighborData(local_interface="GigabitEthernet1/0/2",
                        remote_hostname="Spine-01",
                        remote_interface="Ethernet1/1",
                        remote_platform="Cisco Nexus Operating System"),
        ]

    解析策略：
        - 以 "LLDP neighbor-information of port N [介面名]:" 行分割區塊
        - 在每個區塊中提取 System name → remote_hostname
        - Port ID → remote_interface
        - System description → remote_platform
        - 需要三個必填欄位（local_interface, remote_hostname, remote_interface）
          都存在才會產生一筆 NeighborData

    已知邊界情況：
        - "not advertised" 的欄位不會被 regex 匹配到 → 該欄位為 None
        - 一個 port 可能有多個 LLDP neighbor，但此 parser 只取每個 port 區塊的最後一個
        - 若 System name 為空（某些舊設備），該鄰居不會被輸出
        - 空輸出 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "uplink"
    command = "display lldp neighbor-information"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse HPE Comware LLDP neighbor output.

        Example output format:
        LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:
        LLDP neighbor index       : 1
        Chassis type              : MAC address
        Chassis ID                : 0012-3456-789a
        Port ID type              : Interface name
        Port ID                   : GigabitEthernet1/0/24
        Port description          : not advertised
        System name               : Core-Switch-01
        System description        : HPE Comware Platform Software
        System capabilities supported : Bridge, Router
        System capabilities enabled   : Bridge, Router
        Management address type       : IPv4
        Management address            : 10.0.1.1
        Expired time                  : 112s

        LLDP neighbor-information of port 2 [GigabitEthernet1/0/2]:
        LLDP neighbor index       : 1
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

            # Skip empty lines
            if not line:
                continue

            # Parse local port from header line
            # e.g., "LLDP neighbor-information of port 1 [GigabitEthernet1/0/1]:"
            local_port_match = re.search(
                r"LLDP\s+neighbor-information\s+of\s+port\s+\d+\s+\[([^\]]+)\]",
                line,
                re.IGNORECASE,
            )
            if local_port_match:
                # Save previous neighbor if exists
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

                current_data["local_interface"] = local_port_match.group(1)
                continue

            # Parse System name (e.g., "System name               : Core-Switch-01")
            system_name_match = re.search(
                r"System\s+name\s*:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if system_name_match:
                current_data["remote_hostname"] = system_name_match.group(1)
                continue

            # Parse Port ID (remote interface)
            # e.g., "Port ID                   : GigabitEthernet1/0/24"
            port_id_match = re.search(
                r"Port\s+ID\s*:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if port_id_match:
                current_data["remote_interface"] = port_id_match.group(1)
                continue

            # Parse System description (for platform info)
            # e.g., "System description        : HPE Comware Platform Software"
            system_desc_match = re.search(
                r"System\s+description\s*:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            if system_desc_match:
                current_data["remote_platform"] = system_desc_match.group(1).strip()
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
parser_registry.register(HpeComwareNeighborParser())
