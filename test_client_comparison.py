"""
Test client comparison functionality.

測試客戶端比較的完整流程。
"""
import asyncio
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ClientRecord, ClientComparison, IndicatorResult
from app.core.enums import MaintenancePhase
from app.services.client_comparison_service import ClientComparisonService


async def create_test_data(session: AsyncSession) -> str:
    """建立測試數據。
    
    建立 5 個客戶端的歲修前後記錄，模擬不同的變化情況：
    1. 客戶端 1: 保持不變
    2. 客戶端 2: 埠口變化（critical）
    3. 客戶端 3: 速率變化（warning）
    4. 客戶端 4: 連接中斷（critical）
    5. 客戶端 5: 只有歲修前記錄
    """
    maintenance_id = "maintenance_001"
    now = datetime.utcnow()
    
    records = [
        # 客戶端 1: 保持不變
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.OLD,
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
            ping_latency_ms=5,
            collected_at=now,
        ),
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
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
            ping_latency_ms=5,
            collected_at=now,
        ),
        
        # 客戶端 2: 埠口變化（critical）
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.OLD,
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
            ping_latency_ms=3,
            collected_at=now,
        ),
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
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
            ping_latency_ms=3,
            collected_at=now,
        ),
        
        # 客戶端 3: 速率變化（warning）
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.OLD,
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
            ping_latency_ms=10,
            collected_at=now,
        ),
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
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
            ping_latency_ms=10,
            collected_at=now,
        ),
        
        # 客戶端 4: 連接中斷（critical）
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.OLD,
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
            ping_latency_ms=2,
            collected_at=now,
        ),
        ClientRecord(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
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
            phase=MaintenancePhase.OLD,
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
            ping_latency_ms=8,
            collected_at=now,
        ),
    ]
    
    session.add_all(records)
    await session.commit()
    
    return maintenance_id


async def test_comparison():
    """運行完整的測試流程。"""
    print("=" * 60)
    print("客戶端比較功能測試")
    print("=" * 60)
    
    # 建立引擎和會話
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # 建立表格
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 建立會話
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        # 建立測試數據
        print("\n1️⃣ 建立測試數據...")
        maintenance_id = await create_test_data(session)
        print(f"   ✓ 已建立 5 個客戶端的測試記錄 (maintenance_id: {maintenance_id})")
        
        # 初始化服務
        print("\n2️⃣ 生成客戶端比較...")
        service = ClientComparisonService()
        comparisons = await service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        print(f"   ✓ 已生成 {len(comparisons)} 筆比較記錄")
        
        # 儲存比較結果
        print("\n3️⃣ 儲存比較結果...")
        await service.save_comparisons(comparisons, session)
        print(f"   ✓ 已儲存所有比較記錄")
        
        # 取得摘要
        print("\n4️⃣ 取得比較摘要...")
        summary = await service.get_comparison_summary(
            maintenance_id=maintenance_id,
            session=session,
        )
        print(f"   ✓ 總客戶端數: {summary.get('total', 0)}")
        print(f"   ✓ 保持不變: {summary.get('unchanged', 0)}")
        print(f"   ✓ 有變化: {summary.get('changed', 0)}")
        print(f"   ✓ 重大問題: {summary.get('critical', 0)}")
        print(f"   ✓ 警告問題: {summary.get('warning', 0)}")
        
        # 取得詳細比較列表
        print("\n5️⃣ 取得詳細比較列表...")
        all_comps = await service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        print(f"   ✓ 共 {len(all_comps)} 筆結果")
        
        for idx, comp in enumerate(all_comps, 1):
            print(f"\n   客戶端 {idx}: {comp.mac_address}")
            print(f"   ├─ 嚴重程度: {comp.severity}")
            print(f"   ├─ 是否變化: {'是' if comp.is_changed else '否'}")
            print(f"   ├─ OLD: {comp.old_switch_hostname}:{comp.old_interface_name}")
            print(f"   ├─ NEW: {comp.new_switch_hostname}:{comp.new_interface_name}")
            if comp.differences:
                print(f"   └─ 變化項目: {len(comp.differences)} 項")
                for field, change in comp.differences.items():
                    print(f"      └─ {field}: {change.get('old')} → {change.get('new')}")
        
        # 按嚴重程度篩選
        print("\n6️⃣ 取得重大問題客戶端...")
        critical = await service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            severity="critical",
        )
        print(f"   ✓ 重大問題客戶端: {len(critical)} 個")
        
        for comp in critical:
            print(f"   ├─ {comp.mac_address}")
            if comp.differences:
                for field, change in comp.differences.items():
                    print(f"      └─ {field}: {change.get('old')} → {change.get('new')}")
    
    print("\n" + "=" * 60)
    print("✅ 所有測試完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_comparison())
