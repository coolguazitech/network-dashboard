"""
Cisco NX-OS Neighbor (LLDP) Parser Plugin — 解析 Cisco NX-OS LLDP 鄰居資訊。

CLI 指令：show lldp neighbors detail
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "uplink"    ← 注意是 "uplink" 不是 "neighbor" 或 "lldp"！

輸出模型：list[NeighborData]
    NeighborData 欄位：
        local_interface: str      — 本地介面名稱（如 "Ethernet1/49"），自動正規化 Eth→Ethernet
        remote_hostname: str      — 遠端設備名稱（System Name）
        remote_interface: str     — 遠端介面名稱（Port id），自動正規化 Eth→Ethernet
        remote_platform: str|None — 遠端平台描述（System Description）

重要提醒：
    - NX-OS 使用 LLDP（不是 CDP），因為 NX-OS Spine/Leaf 架構更常用 LLDP
    - Cisco IOS 使用 CDP（show cdp neighbors detail）
    - HPE 也使用 LLDP（display lldp neighbor-information）
    - MockFetcher 必須產生對應的 LLDP 格式（NXOS-LLDP）才能被此 parser 正確解析
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, NeighborData
from app.parsers.registry import parser_registry


class CiscoNxosNeighborParser(BaseParser[NeighborData]):
    """
    Cisco NX-OS LLDP 鄰居 Parser。

    CLI 指令：show lldp neighbors detail
    測試設備：Nexus 9000, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        Chassis id: 0012.3456.789a
        Port id: Ethernet1/1
        Local Port id: Eth1/49
        Port Description: Uplink to Spine-01
        System Name: spine-01.example.com
        System Description: Cisco Nexus Operating System (NX-OS) Software 10.3(3)
        Time remaining: 112 seconds
        System Capabilities: B, R
        Enabled Capabilities: B, R
        Management Address: 10.0.1.1
        Vlan ID: not advertised

        Chassis id: 0012.3456.789b
        Port id: Ethernet1/2
        Local Port id: Eth1/50
        Port Description: Uplink to Spine-02
        System Name: spine-02.example.com
        System Description: Cisco Nexus Operating System (NX-OS) Software 10.3(3)
        ...

    輸出格式（parse() 回傳值）：
    ::

        [
            NeighborData(local_interface="Ethernet1/49",
                        remote_hostname="spine-01.example.com",
                        remote_interface="Ethernet1/1",
                        remote_platform="Cisco Nexus Operating System (NX-OS) Software 10.3(3)"),
            NeighborData(local_interface="Ethernet1/50",
                        remote_hostname="spine-02.example.com",
                        remote_interface="Ethernet1/2",
                        remote_platform="Cisco Nexus Operating System (NX-OS) Software 10.3(3)"),
        ]

    解析策略：
        - 以空行分割鄰居區塊
        - 在每個區塊中提取：
          - "Local Port id: XXX" → local_interface（Eth → Ethernet 正規化）
          - "System Name: XXX" → remote_hostname
          - "Port id: XXX" → remote_interface（Eth → Ethernet 正規化）
          - "System Description: XXX" → remote_platform
        - 注意 "Port id" 和 "Local Port id" 的匹配順序：
          先匹配 "Local Port id"（較具體），再匹配 "Port id"（較一般）

    介面名稱正規化：
        NX-OS 的 LLDP 輸出中 Local Port id 常用縮寫 "Eth1/49"
        此 parser 會自動轉為 "Ethernet1/49"
        同理 remote_interface 的 "Eth" 也會轉為 "Ethernet"

    已知邊界情況：
        - 空行是鄰居區塊的分隔符；如果輸出中沒有空行分隔，解析會有問題
        - "not advertised" 的欄位不會被 regex 匹配到 → 該欄位為 None
        - 最後一個鄰居區塊後面可能沒有空行，需特別處理
        - 某些 NX-OS 版本的輸出可能有額外欄位（如 Auto-negotiation）
          但不影響此 parser（只取已知欄位）
        - 空輸出 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "uplink"
    command = "show lldp neighbors detail"

    def parse(self, raw_output: str) -> list[NeighborData]:
        """
        Parse NX-OS LLDP neighbor output.

        Example output format:
        Chassis id: 0012.3456.789a
        Port id: Ethernet1/1
        Local Port id: Eth1/49
        Port Description: not advertised
        System Name: spine-01.example.com
        System Description: Cisco Nexus Operating System (NX-OS) Software
        Time remaining: 112 seconds
        System Capabilities: B, R
        Enabled Capabilities: B, R
        Management Address: 10.0.1.1
        Vlan ID: not advertised

        Chassis id: 0012.3456.789b
        Port id: Ethernet1/2
        Local Port id: Eth1/50
        System Name: spine-02.example.com
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
                # If we have accumulated data, save it
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

            # Parse Local Port id (e.g., "Local Port id: Eth1/49")
            local_port_match = re.search(
                r"Local\s+Port\s+id:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if local_port_match:
                local_port = local_port_match.group(1)
                # Normalize Eth to Ethernet
                if local_port.startswith("Eth") and not local_port.startswith("Ethernet"):
                    local_port = "Ethernet" + local_port[3:]
                current_data["local_interface"] = local_port
                continue

            # Parse System Name (e.g., "System Name: spine-01.example.com")
            system_name_match = re.search(
                r"System\s+Name:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if system_name_match:
                current_data["remote_hostname"] = system_name_match.group(1)
                continue

            # Parse Port id (remote interface) (e.g., "Port id: Ethernet1/1")
            # Note: This must come after "Local Port id" check
            port_id_match = re.search(
                r"^Port\s+id:\s*(\S+)",
                line,
                re.IGNORECASE,
            )
            if port_id_match:
                port_id = port_id_match.group(1)
                # Normalize Eth to Ethernet
                if port_id.startswith("Eth") and not port_id.startswith("Ethernet"):
                    port_id = "Ethernet" + port_id[3:]
                current_data["remote_interface"] = port_id
                continue

            # Parse System Description (for platform info)
            # e.g., "System Description: Cisco Nexus Operating System (NX-OS) Software"
            system_desc_match = re.search(
                r"System\s+Description:\s*(.+)",
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
parser_registry.register(CiscoNxosNeighborParser())
