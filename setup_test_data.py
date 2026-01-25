#!/usr/bin/env python3
"""
清理資料庫並生成測試數據。

功能：
1. 只保留一個歲修ID (TEST-100)
2. 生成 100 筆比較資料，含異常數據（包含單邊未偵測）
3. 建立 3 個機台種類並分配成員
"""
import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.insert(0, '.')

from app.db.base import get_session_context  # noqa: E402
from app.db.models import (  # noqa: E402
    ClientComparison,
    ClientRecord,
    ClientCategory,
    ClientCategoryMember,
)


MAINTENANCE_ID = "TEST-100"


async def clean_database(session: AsyncSession) -> None:
    """清理資料庫，只保留 TEST-100 的資料。"""
    print("🧹 開始清理資料庫...")
    
    await session.execute(
        delete(ClientComparison).where(
            ClientComparison.maintenance_id != MAINTENANCE_ID
        )
    )
    
    await session.execute(
        delete(ClientRecord).where(
            ClientRecord.maintenance_id != MAINTENANCE_ID
        )
    )
    
    await session.execute(delete(ClientCategoryMember))
    await session.execute(delete(ClientCategory))
    
    await session.commit()
    print("✅ 資料庫清理完成")


async def generate_mac_addresses(count: int) -> list[str]:
    """生成 MAC 地址列表。"""
    macs = []
    for i in range(count):
        suffix = f"{i:02X}"
        mac = f"AA:BB:CC:DD:EE:{suffix}"
        macs.append(mac)
    return macs


async def create_comparison_data(
    session: AsyncSession,
    macs: list[str],
) -> None:
    """建立 100 筆比較資料，包含異常數據。"""
    print("📊 開始生成比較資料...")
    
    await session.execute(
        delete(ClientComparison).where(
            ClientComparison.maintenance_id == MAINTENANCE_ID
        )
    )
    
    now = datetime.utcnow()
    switches = ["SW-PROD-01", "SW-PROD-02", "SW-TEST-01", "SW-CORE-01"]
    
    # 異常分佈
    # 10 筆 critical：埠口變化、斷線
    # 5 筆 critical：OLD有值、NEW未偵測（設備消失）
    # 10 筆 warning：速率降低
    # 5 筆 warning：OLD未偵測、NEW有值（新出現設備）
    # 70 筆正常
    
    comparisons = []
    
    for i, mac in enumerate(macs):
        old_switch = random.choice(switches)
        old_interface = f"Gi1/0/{random.randint(1, 48)}"
        old_ip = f"192.168.{random.randint(1, 10)}.{random.randint(10, 250)}"
        old_vlan = random.choice([100, 200, 300, 400])
        
        if i < 10:
            # Critical: 埠口變化或斷線
            if i % 2 == 0:
                comparison = ClientComparison(
                    maintenance_id=MAINTENANCE_ID,
                    collected_at=now - timedelta(hours=random.randint(0, 48)),
                    mac_address=mac,
                    old_ip_address=old_ip,
                    old_switch_hostname=old_switch,
                    old_interface_name=old_interface,
                    old_vlan_id=old_vlan,
                    old_speed="1G",
                    old_duplex="full",
                    old_link_status="up",
                    old_ping_reachable=True,
                    old_acl_passes=True,
                    new_ip_address=old_ip,
                    new_switch_hostname=old_switch,
                    new_interface_name=old_interface,
                    new_vlan_id=old_vlan,
                    new_speed="1G",
                    new_duplex="full",
                    new_link_status="down",  # 斷線！
                    new_ping_reachable=False,
                    new_acl_passes=True,
                    differences={"link_status": {"old": "up", "new": "down"}},
                    is_changed=True,
                    severity="critical",
                )
            else:
                new_switch = random.choice([s for s in switches if s != old_switch])
                comparison = ClientComparison(
                    maintenance_id=MAINTENANCE_ID,
                    collected_at=now - timedelta(hours=random.randint(0, 48)),
                    mac_address=mac,
                    old_ip_address=old_ip,
                    old_switch_hostname=old_switch,
                    old_interface_name=old_interface,
                    old_vlan_id=old_vlan,
                    old_speed="1G",
                    old_duplex="full",
                    old_link_status="up",
                    old_ping_reachable=True,
                    old_acl_passes=True,
                    new_ip_address=old_ip,
                    new_switch_hostname=new_switch,  # 換交換機
                    new_interface_name=f"Gi1/0/{random.randint(1, 48)}",
                    new_vlan_id=old_vlan,
                    new_speed="1G",
                    new_duplex="full",
                    new_link_status="up",
                    new_ping_reachable=True,
                    new_acl_passes=True,
                    differences={
                        "switch_hostname": {"old": old_switch, "new": new_switch}
                    },
                    is_changed=True,
                    severity="critical",
                )
                
        elif i < 15:
            # Critical: OLD有值，NEW未偵測（設備消失）
            comparison = ClientComparison(
                maintenance_id=MAINTENANCE_ID,
                collected_at=now - timedelta(hours=random.randint(0, 48)),
                mac_address=mac,
                old_ip_address=old_ip,
                old_switch_hostname=old_switch,
                old_interface_name=old_interface,
                old_vlan_id=old_vlan,
                old_speed="1G",
                old_duplex="full",
                old_link_status="up",
                old_ping_reachable=True,
                old_acl_passes=True,
                # NEW 全部為 None（未偵測）
                new_ip_address=None,
                new_switch_hostname=None,
                new_interface_name=None,
                new_vlan_id=None,
                new_speed=None,
                new_duplex=None,
                new_link_status=None,
                new_ping_reachable=None,
                new_acl_passes=None,
                differences={"_status": {"old": "已偵測", "new": "未偵測"}},
                is_changed=True,
                severity="critical",
                notes="🔴 重大：NEW 階段未偵測到該設備",
            )
            
        elif i < 25:
            # Warning: 速率降低
            comparison = ClientComparison(
                maintenance_id=MAINTENANCE_ID,
                collected_at=now - timedelta(hours=random.randint(0, 48)),
                mac_address=mac,
                old_ip_address=old_ip,
                old_switch_hostname=old_switch,
                old_interface_name=old_interface,
                old_vlan_id=old_vlan,
                old_speed="1G",
                old_duplex="full",
                old_link_status="up",
                old_ping_reachable=True,
                old_acl_passes=True,
                new_ip_address=old_ip,
                new_switch_hostname=old_switch,
                new_interface_name=old_interface,
                new_vlan_id=old_vlan,
                new_speed="100M",  # 速率降低
                new_duplex="full",
                new_link_status="up",
                new_ping_reachable=True,
                new_acl_passes=True,
                differences={"speed": {"old": "1G", "new": "100M"}},
                is_changed=True,
                severity="warning",
            )
            
        elif i < 30:
            # Warning: OLD未偵測，NEW有值（新出現設備）
            comparison = ClientComparison(
                maintenance_id=MAINTENANCE_ID,
                collected_at=now - timedelta(hours=random.randint(0, 48)),
                mac_address=mac,
                # OLD 全部為 None（未偵測）
                old_ip_address=None,
                old_switch_hostname=None,
                old_interface_name=None,
                old_vlan_id=None,
                old_speed=None,
                old_duplex=None,
                old_link_status=None,
                old_ping_reachable=None,
                old_acl_passes=None,
                new_ip_address=old_ip,
                new_switch_hostname=old_switch,
                new_interface_name=old_interface,
                new_vlan_id=old_vlan,
                new_speed="1G",
                new_duplex="full",
                new_link_status="up",
                new_ping_reachable=True,
                new_acl_passes=True,
                differences={"_status": {"old": "未偵測", "new": "已偵測"}},
                is_changed=True,
                severity="warning",
                notes="🟡 警告：OLD 階段未偵測到該設備",
            )
            
        else:
            # 正常：無變化
            comparison = ClientComparison(
                maintenance_id=MAINTENANCE_ID,
                collected_at=now - timedelta(hours=random.randint(0, 48)),
                mac_address=mac,
                old_ip_address=old_ip,
                old_switch_hostname=old_switch,
                old_interface_name=old_interface,
                old_vlan_id=old_vlan,
                old_speed="1G",
                old_duplex="full",
                old_link_status="up",
                old_ping_reachable=True,
                old_acl_passes=True,
                new_ip_address=old_ip,
                new_switch_hostname=old_switch,
                new_interface_name=old_interface,
                new_vlan_id=old_vlan,
                new_speed="1G",
                new_duplex="full",
                new_link_status="up",
                new_ping_reachable=True,
                new_acl_passes=True,
                differences=None,
                is_changed=False,
                severity="info",
            )
        
        comparisons.append(comparison)
    
    session.add_all(comparisons)
    await session.commit()
    
    print(f"✅ 已生成 {len(comparisons)} 筆比較資料")
    print("   - Critical (斷線/換埠口): 10 筆")
    print("   - Critical (NEW未偵測): 5 筆")
    print("   - Warning (速率降低): 10 筆")
    print("   - Warning (OLD未偵測): 5 筆")
    print("   - Normal: 70 筆")


async def create_categories_and_members(
    session: AsyncSession,
    macs: list[str],
) -> None:
    """建立 3 個種類並分配成員（分佈在正常和異常數據中）。"""
    print("📂 開始建立機台種類...")
    
    categories_data = [
        {
            "name": "Demo",
            "description": "展示用機台",
            "color": "#3B82F6",
            "sort_order": 0,
        },
        {
            "name": "不斷電機台",
            "description": "歲修期間不關機的參考設備",
            "color": "#EF4444",
            "sort_order": 1,
        },
        {
            "name": "AMHS",
            "description": "自動物料搬運系統",
            "color": "#A855F7",
            "sort_order": 2,
        },
    ]
    
    category_ids = []
    for cat_data in categories_data:
        cat = ClientCategory(**cat_data)
        session.add(cat)
        await session.flush()
        category_ids.append(cat.id)
        print(f"   - 建立種類: {cat_data['name']} (ID: {cat.id})")
    
    # 分配成員（分佈在正常和異常數據中）
    # 比較資料分佈：
    # 0-9: Critical 斷線/換埠口 (10筆)
    # 10-14: Critical NEW未偵測 (5筆)
    # 15-24: Warning 速率降低 (10筆)
    # 25-29: Warning OLD未偵測 (5筆)
    # 30-99: 正常 (70筆)
    
    members = []
    
    # Demo (10台): 5台異常 + 5台正常
    demo_indices = [0, 1, 2, 3, 4,  # 5台 Critical
                    30, 31, 32, 33, 34]  # 5台正常
    for idx in demo_indices:
        members.append(ClientCategoryMember(
            category_id=category_ids[0],
            mac_address=macs[idx],
            description=f"Demo-{idx+1}",
        ))
    
    # 不斷電機台 (13台): 7台異常 + 6台正常
    ref_indices = [10, 11, 12,  # 3台 Critical NEW未偵測
                   15, 16, 17, 18,  # 4台 Warning
                   40, 41, 42, 43, 44, 45]  # 6台正常
    for idx in ref_indices:
        members.append(ClientCategoryMember(
            category_id=category_ids[1],
            mac_address=macs[idx],
            description=f"不斷電-{idx+1}",
        ))
    
    # AMHS (4台): 2台異常 + 2台正常
    amhs_indices = [25, 26,  # 2台 Warning OLD未偵測
                    50, 51]  # 2台正常
    for idx in amhs_indices:
        members.append(ClientCategoryMember(
            category_id=category_ids[2],
            mac_address=macs[idx],
            description=f"AMHS-{idx+1}",
        ))
    
    session.add_all(members)
    await session.commit()
    
    print(f"✅ 已建立 {len(categories_data)} 個種類")
    print("   - Demo: 10 台 (5異常 + 5正常)")
    print("   - 不斷電機台: 13 台 (7異常 + 6正常)")
    print("   - AMHS: 4 台 (2異常 + 2正常)")
    print("   - 未分類: 73 台")


async def main() -> None:
    """主程式。"""
    print("=" * 50)
    print("🚀 開始設定測試數據")
    print("=" * 50)
    
    async with get_session_context() as session:
        await clean_database(session)
        macs = await generate_mac_addresses(100)
        await create_comparison_data(session, macs)
        await create_categories_and_members(session, macs)
    
    print("=" * 50)
    print("✅ 測試數據設定完成！")
    print(f"   歲修 ID: {MAINTENANCE_ID}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
