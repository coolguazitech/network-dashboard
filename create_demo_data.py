"""
創建演示數據到實際數據庫。
"""
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_context
from app.db.models import ClientRecord
from app.core.enums import MaintenancePhase
from app.services.client_comparison_service import ClientComparisonService


async def create_demo_data():
    """建立演示數據。"""
    maintenance_id = "maintenance_001"
    now = datetime.utcnow()
    
    async with get_session_context() as session:
        # 客戶端 1: 保持不變
        records = [
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.PRE,
                mac_address="00:11:22:33:44:11",
                ip_address="10.0.1.11",
                hostname="client-1.example.com",
                switch_hostname="switch-1",
                interface_name="Gi0/1",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=100,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=5.0,
                collected_at=now,
            ),
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.POST,
                mac_address="00:11:22:33:44:11",
                ip_address="10.0.1.11",
                hostname="client-1.example.com",
                switch_hostname="switch-1",
                interface_name="Gi0/1",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=100,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=5.0,
                collected_at=now,
            ),
            
            # 客戶端 2: 埠口變化（critical）
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.PRE,
                mac_address="00:11:22:33:44:22",
                ip_address="10.0.1.22",
                hostname="client-2.example.com",
                switch_hostname="switch-1",
                interface_name="Gi0/2",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=100,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=3.0,
                collected_at=now,
            ),
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.POST,
                mac_address="00:11:22:33:44:22",
                ip_address="10.0.1.22",
                hostname="client-2.example.com",
                switch_hostname="switch-1",
                interface_name="Gi0/3",  # 埠口變了
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=100,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=3.0,
                collected_at=now,
            ),
            
            # 客戶端 3: 速率變化（warning）
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.PRE,
                mac_address="00:11:22:33:44:33",
                ip_address="10.0.1.33",
                hostname="client-3.example.com",
                switch_hostname="switch-2",
                interface_name="Gi0/5",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=200,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=10.0,
                collected_at=now,
            ),
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.POST,
                mac_address="00:11:22:33:44:33",
                ip_address="10.0.1.33",
                hostname="client-3.example.com",
                switch_hostname="switch-2",
                interface_name="Gi0/5",
                speed="100",  # 速率變了
                duplex="full",
                link_status="connected",
                vlan_id=200,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=10.0,
                collected_at=now,
            ),
            
            # 客戶端 4: 連接中斷（critical）
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.PRE,
                mac_address="00:11:22:33:44:44",
                ip_address="10.0.1.44",
                hostname="client-4.example.com",
                switch_hostname="switch-2",
                interface_name="Gi0/6",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=200,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=2.0,
                collected_at=now,
            ),
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.POST,
                mac_address="00:11:22:33:44:44",
                ip_address="10.0.1.44",
                hostname="client-4.example.com",
                switch_hostname="switch-2",
                interface_name="Gi0/6",
                speed="1000",
                duplex="full",
                link_status="down",  # 連接斷掉了
                vlan_id=200,
                acl_passes=True,
                ping_reachable=False,  # Ping 也不通了
                ping_latency_ms=None,
                collected_at=now,
            ),
            
            # 客戶端 5: 只有歲修前記錄
            ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.PRE,
                mac_address="00:11:22:33:44:55",
                ip_address="10.0.1.55",
                hostname="client-5.example.com",
                switch_hostname="switch-3",
                interface_name="Gi0/10",
                speed="1000",
                duplex="full",
                link_status="connected",
                vlan_id=300,
                acl_passes=True,
                ping_reachable=True,
                ping_latency_ms=8.0,
                collected_at=now,
            ),
        ]
        
        session.add_all(records)
        await session.commit()
        
        print(f"✓ 已建立 {len(records)} 筆 ClientRecord 記錄")
        
        # 生成比較結果
        service = ClientComparisonService()
        comparisons = await service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        print(f"✓ 已生成 {len(comparisons)} 筆比較記錄")
        
        # 儲存比較結果
        await service.save_comparisons(comparisons, session)
        
        print(f"✓ 已儲存所有比較記錄到資料庫")
        print(f"\n✅ 演示數據已建立！請在頁面上選擇 maintenance_001 查看結果")


if __name__ == "__main__":
    print("=" * 60)
    print("建立演示數據")
    print("=" * 60)
    asyncio.run(create_demo_data())
