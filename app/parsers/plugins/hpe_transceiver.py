"""
HPE Transceiver Parser Plugin — 解析 HPE ProCurve / Comware 光模組診斷資料。

本模組包含兩個 Parser：
    1. HpeProCurveTransceiverParser — 適用於 HPE ProCurve 系列
       CLI 指令：show interfaces transceiver
    2. HpeComwareTransceiverParser — 適用於 HPE Comware 系列
       CLI 指令：display transceiver

註冊資訊：
    device_type = DeviceType.HPE
    indicator_type = "transceiver"

輸出模型：list[TransceiverData]
    TransceiverData 欄位：
        interface_name: str       — 介面名稱（如 "1", "GigabitEthernet1/0/1"）
        tx_power: float | None    — 發射功率 (dBm)，範圍 -40.0 ~ 10.0
        rx_power: float | None    — 接收功率 (dBm)，範圍 -40.0 ~ 10.0
        temperature: float | None — 溫度 (°C)，範圍 -10.0 ~ 100.0
        voltage: float | None     — 電壓 (V)，範圍 0.0 ~ 10.0
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class HpeComwareTransceiverParser(BaseParser[TransceiverData]):
    """
    HPE Comware 光模組 Parser。

    CLI 指令：display transceiver

    輸入格式（raw_output 範例）：
    ::

        GigabitEthernet1/0/1 transceiver information:
          Transceiver Type               : 1000_BASE_SX_SFP
          Connector Type                 : LC
          Wavelength(nm)                 : 850
          Transfer Distance(m)           : 550(50um/125um OM2)
          Digital Diagnostic Monitoring  : YES
          Vendor Name                    : HP
          Ordering Name                  :
          TX Power    :  -2.31 dBm
          RX Power    :  -3.45 dBm
          Temperature :  35.5  C
          Voltage     :  3.28  V

        GigabitEthernet1/0/2 transceiver information:
          TX Power    :  -1.88 dBm
          RX Power    :  -2.56 dBm
          Temperature :  33.2  C

    輸出格式（parse() 回傳值）：
    ::

        [
            TransceiverData(interface_name="GigabitEthernet1/0/1",
                           tx_power=-2.31, rx_power=-3.45, temperature=35.5),
            TransceiverData(interface_name="GigabitEthernet1/0/2",
                           tx_power=-1.88, rx_power=-2.56, temperature=33.2),
        ]

    解析策略：
        - 以介面名稱行（GigabitEthernet / Ten-GigabitEthernet）分割區塊
        - 在每個區塊中用 regex 提取 TX Power / RX Power / Temperature
        - 至少要有 TX 或 RX Power 才會產生一筆 TransceiverData

    已知邊界情況：
        - Comware 有時不顯示 Voltage 欄位 → voltage 為 None
        - 若介面沒有插入光模組，該介面不會出現在輸出中
        - 空輸出 → 回傳空列表 []
    """

    device_type = DeviceType.HPE
    indicator_type = "transceiver"
    command = "display transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse HPE Comware transceiver output.

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        current_interface: str | None = None
        current_data: dict[str, float | None] = {}

        lines = raw_output.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Match interface line
            interface_match = re.match(
                r"^(GigabitEthernet|Ten-GigabitEthernet)\d+/\d+/\d+",
                line,
            )
            if interface_match:
                if current_interface and self._has_data(current_data):
                    results.append(
                        self._create_data(current_interface, current_data)
                    )
                current_interface = interface_match.group(0)
                current_data = {}
                continue

            # Parse Tx Power
            tx_match = re.search(r"TX Power\s*:\s*([\d.-]+)\s*dBm", line)
            if tx_match:
                current_data["tx_power"] = float(tx_match.group(1))

            # Parse Rx Power
            rx_match = re.search(r"RX Power\s*:\s*([\d.-]+)\s*dBm", line)
            if rx_match:
                current_data["rx_power"] = float(rx_match.group(1))

            # Parse Temperature
            temp_match = re.search(r"Temperature\s*:\s*([\d.-]+)\s*C", line)
            if temp_match:
                current_data["temperature"] = float(temp_match.group(1))

        # Last interface
        if current_interface and self._has_data(current_data):
            results.append(self._create_data(current_interface, current_data))

        return results

    def _has_data(self, data: dict[str, float | None]) -> bool:
        """Check if data has at least tx or rx power."""
        return data.get("tx_power") is not None or \
            data.get("rx_power") is not None

    def _create_data(
        self,
        interface: str,
        data: dict[str, float | None],
    ) -> TransceiverData:
        """Create TransceiverData from parsed data."""
        return TransceiverData(
            interface_name=interface,
            tx_power=data.get("tx_power"),
            rx_power=data.get("rx_power"),
            temperature=data.get("temperature"),
        )


# Register parsers
parser_registry.register(HpeComwareTransceiverParser())
