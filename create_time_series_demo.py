#!/usr/bin/env python3
"""
建立 ClientRecord 時間序列數據，讓圖表有多個時間點可選。

每個時間點有不同的異常變化，模擬實際歲修過程。
"""
import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import delete

import sys
sys.path.insert(0, '.')

from app.db.base import get_session_context
from app.db.models import ClientRecord


MAINTENANCE_ID = "TEST-100"


async def create_time_series_data() -> None:
    """建立多個時間點的 ClientRecord 數據。"""
    print("🕐 開始建立時間序列數據...")
    
    async with get_session_context() as session:
        # 清理現有 ClientRecord
        await session.execute(
            delete(ClientRecord).where(
                ClientRecord.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.commit()
        
        # 基準時間：7天前
        base_time = datetime.utcnow() - timedelta(days=7)
        
        # 生成 100 個 MAC 地址
        macs = [f"AA:BB:CC:DD:EE:{i:02X}" for i in range(100)]
        
        switches = ["SW-PROD-01", "SW-PROD-02", "SW-TEST-01", "SW-CORE-01"]
        
        # 定義每個時間點的數據變化
        # 時間點：0天、1天、2天、3天、5天、7天（共6個時間點）
        time_offsets = [0, 1, 2, 3, 5, 7]
        
        records = []
        
        for day_offset in time_offsets:
            collected_at = base_time + timedelta(days=day_offset)
            print(f"   - 生成時間點: {collected_at.strftime('%Y-%m-%d %H:%M')}")
            
            for i, mac in enumerate(macs):
                # 基本數據
                switch = switches[i % len(switches)]
                interface = f"Gi1/0/{(i % 48) + 1}"
                ip = f"192.168.{(i % 10) + 1}.{(i % 200) + 10}"
                vlan = [100, 200, 300, 400][i % 4]
                speed = "1G"
                duplex = "full"
                link_status = "up"
                ping_reachable = True
                acl_passes = True
                
                # 根據時間點和 MAC 模擬不同的變化
                # 隨著時間推移，異常逐漸修復
                
                if i < 10:
                    # MAC 00-09: 斷線問題，逐步恢復
                    if day_offset < 3:
                        link_status = "down"
                        ping_reachable = False
                    elif day_offset < 5:
                        link_status = "up" if i < 5 else "down"
                        ping_reachable = i < 5
                    else:
                        link_status = "up"
                        ping_reachable = True
                
                elif i < 15:
                    # MAC 0A-0E: 設備消失然後恢復
                    # 前3天有數據，第3-5天消失，最後恢復
                    if 3 <= day_offset < 5:
                        # 這些設備在這段時間不產生記錄（模擬消失）
                        continue
                
                elif i < 25:
                    # MAC 0F-18: 速率逐步降低
                    if day_offset >= 2:
                        speed = "100M"
                
                elif i < 30:
                    # MAC 19-1D: 新出現的設備（前幾天沒數據）
                    if day_offset < 3:
                        # 這些設備在前3天不存在
                        continue
                
                elif i < 40:
                    # MAC 1E-27: 交換機變更
                    if day_offset >= 4:
                        switch = switches[(i + 1) % len(switches)]
                
                # 其餘 MAC (28-63): 正常無變化
                
                record = ClientRecord(
                    maintenance_id=MAINTENANCE_ID,
                    collected_at=collected_at,
                    mac_address=mac,
                    ip_address=ip,
                    switch_hostname=switch,
                    interface_name=interface,
                    vlan_id=vlan,
                    speed=speed,
                    duplex=duplex,
                    link_status=link_status,
                    ping_reachable=ping_reachable,
                    acl_passes=acl_passes,
                )
                records.append(record)
        
        session.add_all(records)
        await session.commit()
        
        print(f"✅ 已建立 {len(records)} 筆時間序列記錄")
        print(f"   - 時間範圍: {base_time.strftime('%Y-%m-%d')} ~ {(base_time + timedelta(days=7)).strftime('%Y-%m-%d')}")
        print(f"   - 時間點數: {len(time_offsets)}")


async def main() -> None:
    """主程式。"""
    print("=" * 50)
    print("🚀 建立時間序列測試數據")
    print("=" * 50)
    
    await create_time_series_data()
    
    print("=" * 50)
    print("✅ 完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
