"""
生成100筆客戶端比較資料用於測試分頁功能
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加項目路徑
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import engine, Base
from app.db.models import ClientRecord, MaintenancePhase
from app.services.client_comparison_service import ClientComparisonService

async def create_100_clients():
    """創建100筆測試客戶端資料"""
    
    # 創建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Keep attributes available after commit to avoid lazy-load round trips during stats
    async with AsyncSession(engine, expire_on_commit=False) as session:
        maintenance_id = "TEST-100"
        
        print(f"生成100筆客戶端資料用於維護ID: {maintenance_id}")
        
        # 清除舊資料
        from sqlalchemy import delete
        await session.execute(delete(ClientRecord).where(ClientRecord.maintenance_id == maintenance_id))
        await session.commit()
        
        clients = []
        
        # 生成100筆資料，分配不同的問題類型
        for i in range(1, 101):
            mac = f"AA:BB:CC:DD:EE:{i:02X}"
            ip = f"192.168.{i // 256}.{i % 256}"
            
            # 決定這個客戶端的狀態
            # 20% 重大問題
            # 30% 警告
            # 50% 正常
            problem_type = i % 10
            
            # OLD 資料（歲修前）
            pre_switch = f"switch-{(i % 10) + 1}"
            pre_port = f"Gi0/{(i % 24) + 1}"
            pre_vlan = 100 + (i % 5) * 100
            
            pre_record = ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.OLD,
                mac_address=mac,
                ip_address=ip,
                switch_hostname=pre_switch,
                interface_name=pre_port,
                vlan_id=pre_vlan,
                speed="1000" if i % 3 != 0 else "100",
                duplex="full",
                link_status="connected",
                ping_reachable=True,
                acl_passes=True,
                collected_at=datetime(2026, 1, 15, 10, 0, 0),
            )
            clients.append(pre_record)
            
            # NEW 資料（歲修後）- 根據問題類型決定變化
            if problem_type in [0, 1]:  # 20% 重大問題
                # 連接埠變化
                post_port = f"Gi0/{(i % 24) + 2}"
                post_link = "connected"
                post_ping = True
            elif problem_type in [2, 3, 4]:  # 30% 警告
                # 速率變化
                post_port = pre_port
                post_link = "connected"
                post_ping = True
                pre_record.speed = "1000"
            else:  # 50% 正常
                post_port = pre_port
                post_link = "connected"
                post_ping = True
            
            post_speed = "1000"
            if problem_type in [2, 3, 4]:  # 警告：速率下降
                post_speed = "100"
            
            # 少數極端情況：連線中斷
            if problem_type == 0:
                post_link = "down"
                post_ping = False
            
            post_record = ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.NEW,
                mac_address=mac,
                ip_address=ip,
                switch_hostname=pre_switch,
                interface_name=post_port,
                vlan_id=pre_vlan,
                speed=post_speed,
                duplex="full",
                link_status=post_link,
                ping_reachable=post_ping,
                acl_passes=True,
                collected_at=datetime(2026, 1, 18, 10, 0, 0),
            )
            clients.append(post_record)
        
        # 批量插入
        session.add_all(clients)
        await session.commit()
        
        print(f"✅ 成功插入 {len(clients)} 筆 ClientRecord (100個客戶端的OLD和NEW)")
        
        # 生成比較結果
        print("\n開始生成比較結果...")
        service = ClientComparisonService()
        comparisons = await service.generate_comparisons(maintenance_id, session)

        # 先計算統計，再寫回資料庫，避免 commit 造成物件過期後觸發異步查詢
        critical_count = 0
        warning_count = 0
        normal_count = 0

        for c in comparisons:
            if c.severity == "critical":
                critical_count += 1
            elif c.severity == "warning":
                warning_count += 1
            elif not c.is_changed:
                normal_count += 1

        await service.save_comparisons(comparisons, session)
        
        print(f"\n📊 比較結果統計:")
        print(f"   總計: {len(comparisons)} 筆")
        print(f"   🔴 重大問題: {critical_count} 筆")
        print(f"   🟡 警告: {warning_count} 筆")
        print(f"   ✅ 正常: {normal_count} 筆")
        print(f"\n✅ 完成！請在前端選擇維護ID: TEST-100")

if __name__ == "__main__":
    asyncio.run(create_100_clients())
