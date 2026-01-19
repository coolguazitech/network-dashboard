"""
創建光模塊的多種問題測試數據。

包括：Tx/Rx 功率低、溫度過高、電壓低、缺失光模塊等
"""
import asyncio
from datetime import datetime

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import CollectionRecord
from app.parsers.registry import auto_discover_parsers


async def create_transceiver_issues():
    """創建光模塊多種問題的測試數據。"""
    
    print("=" * 70)
    print("🔌 創建光模塊多種問題測試數據")
    print("=" * 70)
    
    auto_discover_parsers()
    
    async with get_session_context() as session:
        # 光模塊數據 - 多種問題
        transceiver_data = [
            {
                "interface_name": "Ethernet1/1",
                "tx_power": -15.3,  # ❌ Tx 功率低
                "rx_power": -2.45,
                "temperature": 30.0,
                "voltage": 3.28,
                "serial_number": "FNS001",
                "part_number": "FTLX8571D3BCL",
            },
            {
                "interface_name": "Ethernet1/2",
                "tx_power": -1.0,
                "rx_power": -20.5,  # ❌ Rx 功率低
                "temperature": 28.0,
                "voltage": 3.30,
                "serial_number": "FNS002",
                "part_number": "FTLX8571D3BCL",
            },
            {
                "interface_name": "Ethernet1/3",
                "tx_power": -0.5,
                "rx_power": -2.0,
                "temperature": 62.5,  # ❌ 溫度過高 (>60°C)
                "voltage": 3.29,
                "serial_number": "FNS003",
                "part_number": "FTLX8571D3BCL",
            },
            {
                "interface_name": "Ethernet1/4",
                "tx_power": -1.2,
                "rx_power": -1.8,
                "temperature": 58.0,
                "voltage": 3.15,  # ❌ 電壓低 (<3.2V)
                "serial_number": "FNS004",
                "part_number": "FTLX8571D3BCL",
            },
            {
                "interface_name": "Ethernet1/5",
                "tx_power": None,  # ❌ 光模塊缺失或無法讀取
                "rx_power": None,
                "temperature": None,
                "voltage": None,
                "serial_number": None,
                "part_number": None,
            },
            {
                "interface_name": "Ethernet1/6",
                "tx_power": -0.9,
                "rx_power": -1.9,
                "temperature": 30.0,
                "voltage": 3.28,
                "serial_number": "FNS006",
                "part_number": "FTLX8571D3BCL",
            },
        ]
        
        record = CollectionRecord(
            indicator_type="transceiver",
            switch_hostname="switch-new-01",
            phase=MaintenancePhase.POST,
            maintenance_id="2026Q1-ANNUAL",
            raw_data="[mock transceiver data with various issues]",
            parsed_data=transceiver_data,
            collected_at=datetime.now(),
        )
        session.add(record)
        
        await session.commit()
        
        print("\n✅ 光模塊多種問題數據創建完成！")
        print("\n問題類型：")
        print("  ❌ Ethernet1/1 - Tx 功率低 (-15.3 dBm, 預期: > -12 dBm)")
        print("  ❌ Ethernet1/2 - Rx 功率低 (-20.5 dBm, 預期: > -18 dBm)")
        print("  ❌ Ethernet1/3 - 溫度過高 (62.5°C, 預期: < 60°C)")
        print("  ❌ Ethernet1/4 - 電壓低 (3.15V, 預期: > 3.2V)")
        print("  ❌ Ethernet1/5 - 光模塊缺失或無法讀取")
        print("  ✅ Ethernet1/6 - 正常")
        print("\n預期結果：")
        print("  • 光模塊: 1/6 通過 = 17% (5 個失敗)")
        print("\n請刷新 Dashboard 查看詳細失敗原因！")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_transceiver_issues())
