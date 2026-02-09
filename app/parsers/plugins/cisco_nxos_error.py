"""
Cisco NX-OS Interface Error Parser — 解析 Cisco NX-OS 介面錯誤計數器。

CLI 指令：show interface counters errors（注意：NX-OS 是 "interface" 不是 "interfaces"）
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "error_count"

輸出模型：list[InterfaceErrorData]
    InterfaceErrorData 欄位：
        interface_name: str    — 介面名稱（如 "Eth1/1"）
        crc_errors: int        — CRC 錯誤（映射自 FCS-Err 欄位）
        input_errors: int      — 輸入錯誤（映射自 Rcv-Err 欄位）
        output_errors: int     — 輸出錯誤（預設 0，此 parser 未映射 Xmit-Err）
        collisions: int        — 碰撞計數（預設 0）
        giants: int            — 超大封包計數（預設 0）
        runts: int             — 過小封包計數（預設 0）

NX-OS vs IOS 差異：
    - NX-OS 的錯誤計數器欄位更細（Align-Err, FCS-Err, Xmit-Err, Rcv-Err, UnderSize, OutDiscards）
    - NX-OS 指令是 "show interface counters errors"（interface 無 s）
    - NX-OS 介面名稱用 "Eth1/1" 而非 "Gi1/0/1"
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, InterfaceErrorData
from app.parsers.registry import parser_registry


class CiscoNxosErrorParser(BaseParser[InterfaceErrorData]):
    """
    Cisco NX-OS 介面錯誤計數器 Parser。

    CLI 指令：show interface counters errors
    測試設備：Nexus 9000, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        --------------------------------------------------------------------------------
        Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        --------------------------------------------------------------------------------
        Eth1/1                0          0          0          0          0           0
        Eth1/2               10          5          0          3          0           0
        Eth1/3                0          0          2          0          0           1
        Eth1/49               0          0          0          0          0           0

    輸出格式（parse() 回傳值）：
    ::

        [
            InterfaceErrorData(interface_name="Eth1/1", crc_errors=0,
                              input_errors=0, output_errors=0),
            InterfaceErrorData(interface_name="Eth1/2", crc_errors=5,
                              input_errors=3, output_errors=0),
            InterfaceErrorData(interface_name="Eth1/3", crc_errors=0,
                              input_errors=0, output_errors=0),
            InterfaceErrorData(interface_name="Eth1/49", crc_errors=0,
                              input_errors=0, output_errors=0),
        ]

    NX-OS 欄位映射：
        Align-Err  → 忽略（未使用）
        FCS-Err    → crc_errors（FCS = Frame Check Sequence ≈ CRC）
        Xmit-Err   → 忽略（程式碼中有註解但未啟用）
        Rcv-Err    → input_errors
        UnderSize  → 忽略（原始碼中有 runts 映射但未啟用）
        OutDiscards → 忽略

    解析策略：
        - 用 regex 匹配 "介面名  數字  數字  數字  數字  數字  數字"（7 欄位）
        - "---" 分隔線和 "Port" 表頭行不會被 regex 匹配到
        - 只取 FCS-Err（第 3 欄）和 Rcv-Err（第 5 欄）

    已知邊界情況：
        - NX-OS 的表格可能有額外欄位（如某些版本有 Giants 欄位）
          但此 regex 要求恰好 7 個欄位
        - output_errors 目前固定為 0（Xmit-Err 未映射）
        - collisions, giants, runts 均為預設值 0
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "error_count"
    command = "show interface counters errors"

    def parse(self, raw_output: str) -> list[InterfaceErrorData]:
        """
        Parse 'show interface counters errors' output.
        
        Example:
        --------------------------------------------------------------------------------
        Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
        --------------------------------------------------------------------------------
        Eth1/1                0          0          0          0          0           0
        Eth1/2               10          5          0          0          0           0
        """
        results = []
        
        # Regex to capture error line
        # Group 1: Interface
        # Group 2-N: Error counts (we only care about some)
        # Note: Columns may vary slightly, but usually:
        # Port, Align-Err, FCS-Err, Xmit-Err, Rcv-Err, UnderSize, OutDiscards
        pattern = re.compile(
            r"^([A-Za-z0-9\/]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue
                
            interface = match.group(1)
            # align_err = int(match.group(2))
            fcs_err = int(match.group(3))
            # xmit_err = int(match.group(4))
            rcv_err = int(match.group(5))
            # undersize = int(match.group(6))
            # out_discards = int(match.group(7))
            
            # For simplicity, we map:
            # crc_errors = fcs_err
            # input_errors = rcv_err
            # output_errors = xmit_err (simplified)
            
            # Only include if there are errors (optional, but saves space)
            # Or always include to show status? Usually always include for validation.
            
            results.append(
                InterfaceErrorData(
                    interface_name=interface,
                    crc_errors=fcs_err,
                    input_errors=rcv_err,
                    # output_errors=xmit_err,
                    # collisions=0, # Not in this command usually
                    # giants=0,
                    # runts=undersize
                )
            )
            
        return results


# Register parsers
parser_registry.register(CiscoNxosErrorParser())
