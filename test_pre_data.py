"""
創建 PRE phase 測試數據用於對比。
"""
import asyncio
from datetime import datetime

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import CollectionRecord
from app.parsers.registry import auto_discover_parsers


async def create_pre_data():
    """創建 PRE phase 數據。"""
    
    print("=" * 70)
    print("📊 創建 PRE phase 對比數據")
    print("=" * 70)
    
    auto_discover_parsers()
    
    async with get_session_context() as session:
        # PRE 光模塊數據 - 有更多問題
        transceiver_data_pre = [
            {
                "interface_name": "Ethernet1/1",
                "tx_power": -14.0,  # ❌ 問題
                "rx_power": -19.0,  # ❌ 問題
                "temperature": 65.0,  # ❌ 溫度過高
                "voltage": 3.1,  # ❌ 電壓低
                "serial_number": "OLD001",
                "part_number": "OLD",
            },
            {
                "interface_name": "Ethernet1/2",
                "tx_power": -13.0,  # ❌ 問題
                "rx_power": -2.0,
                "temperature": 60.0,
                "voltage": 3.2,
                "serial_number": "OLD002",
                "part_number": "OLD",
            },
            {
                "interface_name": "Ethernet1/3",
                "tx_power": -0.5,
                "rx_power": -2.0,
                "temperature": 58.0,
                "voltage": 3.28,
                "serial_number": "OLD003",
                "part_number": "OLD",
            },
        ]
        
        record_pre = CollectionRecord(
            indicator_type="transceiver",
            switch_hostname="switch-old-01",
            phase=MaintenancePhase.OLD,
            maintenance_id="2026Q1-ANNUAL",
            raw_data="[mock pre-maintenance data]",
            parsed_data=transceiver_data_pre,
            collected_at=datetime.now(),
        )
        session.add(record_pre)
        
        # PRE 版本數據
        version_data_pre = {
            "version": "9.2(8)",  # 舊版本
            "model": "N9K-C9332PQ",
        }
        
        record_version_pre = CollectionRecord(
            indicator_type="version",
            switch_hostname="switch-old-01",
            phase=MaintenancePhase.OLD,
            maintenance_id="2026Q1-ANNUAL",
            raw_data="[mock version data]",
            parsed_data=version_data_pre,
            collected_at=datetime.now(),
        )
        session.add(record_version_pre)
        
        await session.commit()
        
        print("\n✅ OLD phase 數據創建完成！")
        print("\nOLD 光模塊統計:")
        print("  • Ethernet1/1 - 有 4 個問題 (Tx低、Rx低、溫度高、電壓低)")
        print("  • Ethernet1/2 - 有 1 個問題 (Tx低)")
        print("  • Ethernet1/3 - 正常")
        print("  → OLD 通過率: 1/3 = 33%")
        print("\nNEW 光模塊統計 (來自之前的測試):")
        print("  → NEW 通過率: 1/6 = 17%")
        print("\n現在訪問 API 可以看到對比結果！")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_pre_data())
