"""
Cisco NX-OS Power Supply Parser — 解析 Cisco NX-OS 電源供應器狀態。

CLI 指令：show environment power
註冊資訊：
    device_type = DeviceType.CISCO_NXOS
    indicator_type = "power"

輸出模型：list[PowerData]
    PowerData 欄位：
        ps_id: str                    — 電源 ID（如 "1", "2"）
        status: str                   — 自動正規化為 OperationalStatus 枚舉值
        input_status: str | None      — NX-OS 不提供獨立 input status，為 None
        output_status: str | None     — 設為與 status 相同
        capacity_watts: float | None  — 額定瓦數（如 650.0）
        actual_output_watts: float|None — 實際輸出瓦數（如 124.0）
"""
from __future__ import annotations

import re

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, PowerData
from app.parsers.registry import parser_registry


class CiscoNxosPowerParser(BaseParser[PowerData]):
    """
    Cisco NX-OS 電源供應器 Parser。

    CLI 指令：show environment power
    測試設備：Nexus 9000, 9300 系列

    輸入格式（raw_output 範例）：
    ::

        Power                              Actual        Total
        Supply    Model                    Output     Capacity    Status
                                           (Watts)     (Watts)
        -------  -------------------  -----------  -----------  --------------
        1        NXA-PAC-650W-PI              124          650     Ok
        2        NXA-PAC-650W-PI              132          650     Ok

        Voltage: 12 Volts

                  Actual        Total
        Module    Output     Capacity    Status
                  (Watts)     (Watts)
        -------  -----------  ----------  ----------
        1           95.00       N/A        Powered-Up
        ...

    輸出格式（parse() 回傳值）：
    ::

        [
            PowerData(ps_id="1", status="ok", capacity_watts=650.0,
                      actual_output_watts=124.0, input_status=None,
                      output_status="ok"),
            PowerData(ps_id="2", status="ok", capacity_watts=650.0,
                      actual_output_watts=132.0, input_status=None,
                      output_status="ok"),
        ]

    解析策略：
        - 跳過表頭（"Power", "Supply", "---", "Voltage" 開頭的行）
        - 用 regex 匹配 "ID  Model  Output  Capacity  Status" 格式
        - Output 和 Capacity 直接轉為 float
        - input_status 不可得（NX-OS 不區分），設為 None
        - output_status 設為與 Status 欄位相同

    已知邊界情況：
        - NX-OS 輸出包含 Power Supply 區段和 Module 區段
          此 parser 只解析 Power Supply 區段（因為 Module 行的格式不同）
        - 某些 Nexus 型號的 Status 可能是 "Powered-Up" 而非 "Ok"
          → OperationalStatus validator 會將其映射為 "unknown"
        - 若需要處理 "Powered-Up" 為正常狀態，需在 .env 的
          OPERATIONAL_HEALTHY_STATUSES 中加入
        - 空輸出或無匹配行 → 回傳空列表 []
    """

    device_type = DeviceType.CISCO_NXOS
    indicator_type = "power"
    command = "show environment power"

    def parse(self, raw_output: str) -> list[PowerData]:
        """
        Parse 'show environment power' output.
        
        Example:
        Power                              Actual        Total
        Supply    Model                    Output     Capacity    Status
                                           (Watts)     (Watts)
        -------  -------------------  -----------  -----------  --------------
        1        NXA-PAC-650W-PI              124          650     Ok
        2        NXA-PAC-650W-PI              132          650     Ok
        """
        results = []
        
        # Regex for table rows
        # 1        NXA-PAC-650W-PI              124          650     Ok
        # Group 1: ID
        # Group 2: Model
        # Group 3: Output
        # Group 4: Capacity
        # Group 5: Status
        pattern = re.compile(
            r"^(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(.+)$",
            re.MULTILINE
        )
        
        lines = raw_output.strip().splitlines()
        
        for line in lines:
            line = line.strip()
            # Skip header lines
            if line.startswith("Power") or line.startswith("Supply") or line.startswith("---") or line.startswith("Voltage"):
                continue
                
            match = pattern.match(line)
            if not match:
                continue
                
            ps_id = match.group(1)
            output = float(match.group(3))
            capacity = float(match.group(4))
            status = match.group(5).strip()
            
            results.append(
                PowerData(
                    ps_id=ps_id,
                    status=status,
                    capacity_watts=capacity,
                    actual_output_watts=output,
                    input_status=None,  # NXOS output usually implies input ok if status is ok
                    output_status=status
                )
            )
            
        return results


# Register parsers
parser_registry.register(CiscoNxosPowerParser())
