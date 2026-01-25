"""
創建 Uplink 失敗測試數據。

這樣可以看到指標排序效果。
"""
import asyncio
from datetime import datetime

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import CollectionRecord
from app.parsers.registry import auto_discover_parsers


async def create_uplink_failure_data():
    """創建 Uplink 失敗的測試數據。"""
    
    print("=" * 70)
    print("🔧 創建 Uplink 失敗測試數據")
    print("=" * 70)
    
    auto_discover_parsers()
    
    async with get_session_context() as session:
        # Uplink 數據 - 故意製造 2 個失敗
        uplink_data = [
            {
                "local_interface": "Ethernet1/49",
                "remote_hostname": "spine-01",
                "remote_interface": "Ethernet1/1",
            },
            {
                "local_interface": "Ethernet1/50",
                "remote_hostname": "spine-03",  # ❌ 錯誤！期望是 spine-02
                "remote_interface": "Ethernet1/2",
            },
        ]
        
        record = CollectionRecord(
            indicator_type="uplink",
            switch_hostname="switch-new-02",
            phase=MaintenancePhase.NEW,
            maintenance_id="2026Q1-ANNUAL",
            raw_data="[mock uplink data]",
            parsed_data=uplink_data,
            collected_at=datetime.now(),
        )
        session.add(record)
        
        # 另一個設備也有失敗
        uplink_data2 = [
            {
                "local_interface": "Ethernet1/49",
                "remote_hostname": "wrong-spine",  # ❌ 完全錯誤的鄰居
                "remote_interface": "Ethernet1/1",
            },
        ]
        
        record2 = CollectionRecord(
            indicator_type="uplink",
            switch_hostname="switch-new-03",
            phase=MaintenancePhase.NEW,
            maintenance_id="2026Q1-ANNUAL",
            raw_data="[mock uplink data]",
            parsed_data=uplink_data2,
            collected_at=datetime.now(),
        )
        session.add(record2)
        
        await session.commit()
        
        print("\n✅ Uplink 失敗數據創建完成！")
        print("\n預期結果：")
        print("  • 光模塊: 33% (6 失敗)")
        print("  • Uplink: ~67% (2 失敗)  ⬅️ 新增失敗")
        print("  • 版本: 100% (0 失敗)")
        print("\n排序後順序：")
        print("  1️⃣ 光模塊 (失敗最多)")
        print("  2️⃣ Uplink (有失敗)")
        print("  3️⃣ 版本 (全部通過)")
        print("\n請刷新 Dashboard 查看效果！")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_uplink_failure_data())
