"""
Cisco NX-OS Transceiver Parser Plugin — 解析 Cisco NX-OS 光模組診斷資料。

CLI 指令：show interface transceiver（注意：NX-OS 是 "interface" 不是 "interfaces"）
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "transceiver"

輸出模型：list[TransceiverData]
    TransceiverData 欄位：
        interface_name: str       — 介面名稱（如 "Ethernet1/1"）
        tx_power: float | None    — 發射功率 (dBm)，範圍 -40.0 ~ 10.0
        rx_power: float | None    — 接收功率 (dBm)，範圍 -40.0 ~ 10.0
        temperature: float | None — 溫度 (°C)，範圍 -10.0 ~ 100.0
        voltage: float | None     — 電壓 (V)，範圍 0.0 ~ 10.0

NX-OS vs IOS 差異：
    - NX-OS 的指令是 "show interface transceiver"（無 s）
    - NX-OS 輸出是多行 key-value 格式（非表格）
    - NX-OS 介面名稱用 "Ethernet1/1" 而非 "Gi1/0/1"
    - NX-OS 會顯示 "transceiver is not present" 的介面
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class CiscoNxosTransceiverParser(BaseParser[TransceiverData]):
    """
    Cisco NX-OS 光模組 Parser。

    CLI 指令：show interface transceiver
    測試設備：Nexus 9000, 9300, 9500 系列

    輸入格式（raw_output 範例）：
    ::

        Ethernet1/1
            transceiver is present
            type is QSFP-40G-SR4
            name is CISCO-FINISAR
            part number is FTLX8571D3BCL-C2
            serial number is FNS12345678
            nominal bitrate is 10300 MBit/sec per channel
            Link length supported for 50/125um OM3 fiber is 100 m
            cisco id is --
            cisco extended id number is 4
            Temperature            30.32 C
            Voltage                3.28 V
            Current                6.45 mA
            Tx Power               -1.23 dBm
            Rx Power               -2.45 dBm

        Ethernet1/2
            transceiver is present
            type is 10Gbase-SR
            Temperature            28.50 C
            Voltage                3.30 V
            Tx Power               -2.10 dBm
            Rx Power               -3.80 dBm

        Ethernet1/5
            transceiver is not present

    輸出格式（parse() 回傳值）：
    ::

        [
            TransceiverData(interface_name="Ethernet1/1",
                           tx_power=-1.23, rx_power=-2.45,
                           temperature=30.32, voltage=3.28),
            TransceiverData(interface_name="Ethernet1/2",
                           tx_power=-2.10, rx_power=-3.80,
                           temperature=28.50, voltage=3.30),
            TransceiverData(interface_name="Ethernet1/5",
                           tx_power=None, rx_power=None,
                           temperature=None, voltage=None),
        ]

    解析策略：
        - 以 "Ethernet" 開頭的行分割區塊
        - 檢查 "transceiver is not present" → 產生全 None 的 TransceiverData
        - 在每個區塊中用 regex 提取 Temperature / Voltage / Tx Power / Rx Power
        - NX-OS 格式一致性較高，regex 比較穩定

    已知邊界情況：
        - "transceiver is not present" 的介面仍會產生一筆 TransceiverData（所有值為 None）
          這與 IOS parser 不同（IOS 不顯示無模組的介面）
        - Nexus 9000 的 QSFP 介面可能有多個 lane（lane 1-4），
          此 parser 只取介面級別的總值
        - 介面名稱格式：Ethernet1/1, Ethernet1/1/1（breakout 模式）
        - 空輸出 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "transceiver"
    command = "show interface transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse NX-OS transceiver output.

        Example output format:
        Ethernet1/1
            transceiver is present
            type is QSFP-40G-SR4
            name is CISCO-FINISAR
            part number is FTLX8571D3BCL-C2
            serial number is FNS12345678
            Temperature            30.32 C
            Voltage                3.28 V
            Current                6.45 mA
            Tx Power               -1.23 dBm
            Rx Power               -2.45 dBm

        Ethernet1/5
            transceiver is not present

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        current_interface: str | None = None
        current_data: dict[str, float | str | None] = {}
        is_present: bool = True  # 新增：追蹤光模塊是否存在

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Match interface line (e.g., "Ethernet1/1")
            interface_match = re.match(
                r"^(Ethernet\d+/\d+(?:/\d+)?)",
                line,
            )
            if interface_match:
                # Save previous interface data if exists
                if current_interface:
                    results.append(
                        self._create_transceiver_data(
                            current_interface,
                            current_data,
                            is_present,  # 傳遞光模塊存在狀態
                        )
                    )
                current_interface = interface_match.group(1)
                current_data = {}
                is_present = True  # 重置狀態
                continue

            # 檢測光模塊不存在
            if re.search(r"transceiver\s+is\s+not\s+present", line, re.IGNORECASE):
                is_present = False
                continue

            # Parse temperature
            temp_match = re.search(
                r"Temperature\s+([\d.-]+)\s*C",
                line,
                re.IGNORECASE,
            )
            if temp_match:
                current_data["temperature"] = float(temp_match.group(1))

            # Parse voltage
            voltage_match = re.search(
                r"Voltage\s+([\d.]+)\s*V",
                line,
                re.IGNORECASE,
            )
            if voltage_match:
                current_data["voltage"] = float(voltage_match.group(1))

            # Parse Tx Power
            tx_match = re.search(
                r"Tx\s+Power\s+([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if tx_match:
                current_data["tx_power"] = float(tx_match.group(1))

            # Parse Rx Power
            rx_match = re.search(
                r"Rx\s+Power\s+([\d.-]+)\s*dBm",
                line,
                re.IGNORECASE,
            )
            if rx_match:
                current_data["rx_power"] = float(rx_match.group(1))

        # Don't forget the last interface
        if current_interface:
            results.append(
                self._create_transceiver_data(
                    current_interface,
                    current_data,
                    is_present,
                )
            )

        return results

    def _create_transceiver_data(
        self,
        interface: str,
        data: dict[str, float | str | None],
        is_present: bool = True,
    ) -> TransceiverData:
        """
        Create TransceiverData from parsed data.
        
        如果光模塊不存在，所有值設為 None。
        """
        if not is_present:
            # 光模塊不存在，返回空數據但保留接口名稱
            return TransceiverData(
                interface_name=interface,
                tx_power=None,
                rx_power=None,
                temperature=None,
                voltage=None,
            )

        return TransceiverData(
            interface_name=interface,
            tx_power=data.get("tx_power"),  # type: ignore
            rx_power=data.get("rx_power"),  # type: ignore
            temperature=data.get("temperature"),  # type: ignore
            voltage=data.get("voltage"),  # type: ignore
        )


# Register the parser
parser_registry.register(CiscoNxosTransceiverParser())
