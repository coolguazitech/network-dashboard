"""
Parser Plugins 套件 — 所有 parser plugin 的集中入口。

==========================================================================
重要：在這裡 import 你的新 parser 模組，才能觸發自動註冊！
==========================================================================

工作原理：
    1. 每個 parser plugin 檔案（如 hpe_fan.py）在底部呼叫
       parser_registry.register(MyParser())
    2. 當本檔案 (__init__.py) import 該模組時，模組底部的程式碼執行
    3. Parser 就被註冊進全域 registry 了

如何新增一個 parser：
    1. 在本目錄建立新檔案（如 aruba_transceiver.py）
    2. 在檔案中實作 Parser 類別（見 BaseParser docstring）
    3. 在檔案底部 parser_registry.register(ArubaTransceiverParser())
    4. 在下方的 import 列表中加上：from . import aruba_transceiver
    5. 完成！系統啟動時自動載入。

命名慣例：
    {vendor}_{indicator_type}.py
    例如：hpe_fan.py, cisco_ios_transceiver.py, cisco_nxos_version.py

特殊情況：
    - ping.py：跨平台通用，device_type=None 的 generic parser
"""
from . import (
    cisco_ios_transceiver,
    # cisco_nxos_transceiver,  # 故意不載入：用於演示 CollectionError（CORE 設備 transceiver 會顯示紫色錯誤）
    hpe_transceiver,
    cisco_ios_port_channel,
    cisco_nxos_port_channel,
    hpe_port_channel,
    cisco_ios_power,
    cisco_nxos_power,
    hpe_power,
    cisco_ios_fan,
    cisco_nxos_fan,
    hpe_fan,
    cisco_ios_error,
    cisco_nxos_error,
    hpe_error,
    ping,
    cisco_nxos_neighbor,
    hpe_neighbor,
    cisco_ios_version,
    cisco_nxos_version,
    hpe_version,
    cisco_ios_neighbor,
)
