"""
Cisco IOS Transceiver Parser Plugin — 解析 Cisco IOS 光模組診斷資料。

CLI 指令：show interfaces transceiver
註冊資訊：
    device_type = DeviceType.CISCO_IOS
    indicator_type = "transceiver"

輸出模型：list[TransceiverData]
    TransceiverData 欄位：
        interface_name: str       — 介面名稱（如 "Gi1/0/1"）
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


class CiscoIosTransceiverParser(BaseParser[TransceiverData]):
    """
    Cisco IOS 光模組 Parser。

    CLI 指令：show interfaces transceiver
    測試設備：Catalyst 3750, 9200, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        If device is different different different, different header formats may appear.
        The most common format:

                                         Optical   Optical
                       Temperature  Voltage  Tx Power  Rx Power
        Port           (Celsius)    (Volts)  (dBm)     (dBm)
        ---------      -----------  -------  --------  --------
        Gi1/0/1        32.5         3.29     -2.1      -3.5
        Gi1/0/2        31.8         3.30     -1.8      -2.9
        Te1/1/1        28.0         3.31      0.5      -1.2

    輸出格式（parse() 回傳值）：
    ::

        [
            TransceiverData(interface_name="Gi1/0/1", tx_power=-2.1,
                           rx_power=-3.5, temperature=32.5, voltage=3.29),
            TransceiverData(interface_name="Gi1/0/2", tx_power=-1.8,
                           rx_power=-2.9, temperature=31.8, voltage=3.30),
            TransceiverData(interface_name="Te1/1/1", tx_power=0.5,
                           rx_power=-1.2, temperature=28.0, voltage=3.31),
        ]

    解析策略：
        - 找到 "----" 分隔線後進入資料區
        - 每行用空白分割：Port  Temp  Voltage  TxPower  RxPower（5 欄位）
        - N/A 和 "-" 值會解析為 None

    已知邊界情況：
        - 某些 Catalyst 型號的 header 格式略有不同（多行 header）
          但分隔線 "----" 下方的資料格式一致
        - 無 SFP 模組的 port 不會出現在輸出中
        - Tx/Rx 為 "N/A" 的行會被保留但值為 None
          → 至少要有 tx_power 或 rx_power 非 None 才產生 TransceiverData
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_IOS
    indicator_type = "transceiver"
    command = "show interfaces transceiver"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        """
        Parse IOS transceiver output.

        Example output format (table style):
                                     Optical   Optical
                   Temperature  Voltage  Tx Power  Rx Power
        Port       (Celsius)    (Volts)  (dBm)     (dBm)
        ---------  -----------  -------  --------  --------
        Gi1/0/1    32.5         3.29     -2.1      -3.5
        Gi1/0/2    31.8         3.30     -1.8      -2.9

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TransceiverData]: Parsed transceiver data
        """
        results: list[TransceiverData] = []
        lines = raw_output.strip().split("\n")

        # Find the data section (after the header line with dashes)
        in_data_section = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Check for separator line (----)
            if re.match(r"^[\s-]+$", line):
                in_data_section = True
                continue

            if not in_data_section:
                continue

            # Parse data line
            # Format: Port  Temp  Voltage  TxPower  RxPower
            parts = line.split()
            if len(parts) >= 5:
                try:
                    interface = parts[0]
                    temp = self._parse_float(parts[1])
                    voltage = self._parse_float(parts[2])
                    tx_power = self._parse_float(parts[3])
                    rx_power = self._parse_float(parts[4])

                    if tx_power is not None or rx_power is not None:
                        results.append(
                            TransceiverData(
                                interface_name=interface,
                                tx_power=tx_power,
                                rx_power=rx_power,
                                temperature=temp,
                                voltage=voltage,
                            )
                        )
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue

        return results

    def _parse_float(self, value: str) -> float | None:
        """Parse float value, returning None for N/A or invalid."""
        if value.lower() in ("n/a", "-", "--", ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None


# Register the parser
parser_registry.register(CiscoIosTransceiverParser())
