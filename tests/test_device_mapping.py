"""
設備對應測試腳本

測試場景：
1. 建立新歲修，設定設備對應關係 (old_hostname → new_hostname)
2. 產生 OLD 階段資料：MAC 連接到舊設備
3. 產生 NEW 階段資料：MAC 連接到新設備
4. 驗證比較邏輯是否正確識別：
   - 符合對應的設備變化 → info（正常）
   - 不符合對應的設備變化 → warning
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

sys.path.insert(0, "/Users/coolguazi/Project/ClineTest/network_dashboard")


async def setup_test():
    """設定測試環境"""
    from app.db.base import get_session_context
    from app.db.models import (
        MaintenanceConfig,
        MaintenanceDeviceList,
        MaintenanceMacList,
        ClientRecord,
        ClientComparison,
    )
    from app.core.enums import MaintenancePhase, ClientDetectionStatus
    from sqlalchemy import delete, select

    print("=" * 80)
    print("設備對應測試 (Device Mapping Test)")
    print("=" * 80)

    maintenance_id = "2026-DEVICE-MAPPING-TEST"

    async with get_session_context() as session:
        # 1. 刪除舊的測試資料
        print("\n📋 [1] 清理舊的測試資料...")

        # 刪除舊的 ClientRecord
        await session.execute(
            delete(ClientRecord).where(ClientRecord.maintenance_id == maintenance_id)
        )
        # 刪除舊的 ClientComparison
        await session.execute(
            delete(ClientComparison).where(ClientComparison.maintenance_id == maintenance_id)
        )
        # 刪除舊的 MaintenanceMacList
        await session.execute(
            delete(MaintenanceMacList).where(MaintenanceMacList.maintenance_id == maintenance_id)
        )
        # 刪除舊的 MaintenanceDeviceList
        await session.execute(
            delete(MaintenanceDeviceList).where(MaintenanceDeviceList.maintenance_id == maintenance_id)
        )
        # 刪除舊的 MaintenanceConfig
        await session.execute(
            delete(MaintenanceConfig).where(MaintenanceConfig.maintenance_id == maintenance_id)
        )
        await session.commit()
        print("   ✅ 舊資料已清理")

        # 2. 建立新的歲修設定
        print("\n📋 [2] 建立新的歲修設定...")
        config = MaintenanceConfig(
            maintenance_id=maintenance_id,
            name="設備對應測試",
            start_date=datetime.now(timezone.utc).date(),
            end_date=(datetime.now(timezone.utc) + timedelta(days=7)).date(),
            is_active=True,
        )
        session.add(config)
        await session.commit()
        print(f"   ✅ 歲修設定已建立: {maintenance_id}")

        # 3. 建立設備對應關係
        print("\n📋 [3] 建立設備對應關係...")
        device_mappings = [
            # old_hostname → new_hostname
            ("SW-OLD-01", "SW-NEW-01"),  # 正常對應
            ("SW-OLD-02", "SW-NEW-02"),  # 正常對應
            ("SW-OLD-03", "SW-NEW-03"),  # 正常對應
        ]

        for old_hostname, new_hostname in device_mappings:
            device = MaintenanceDeviceList(
                maintenance_id=maintenance_id,
                old_hostname=old_hostname,
                old_ip_address=f"192.168.1.{hash(old_hostname) % 255}",
                old_vendor="Cisco-IOS",
                new_hostname=new_hostname,
                new_ip_address=f"192.168.2.{hash(new_hostname) % 255}",
                new_vendor="Cisco-IOS",
            )
            session.add(device)
            print(f"   - {old_hostname} → {new_hostname}")

        await session.commit()
        print("   ✅ 設備對應已建立")

        # 4. 建立 MAC 清單
        print("\n📋 [4] 建立 MAC 清單...")
        mac_list = [
            # MAC, 預期行為
            ("AA:BB:CC:DD:01:01", "正常對應：SW-OLD-01 → SW-NEW-01"),
            ("AA:BB:CC:DD:02:02", "正常對應：SW-OLD-02 → SW-NEW-02"),
            ("AA:BB:CC:DD:03:03", "正常對應：SW-OLD-03 → SW-NEW-03"),
            ("AA:BB:CC:DD:04:04", "異常：SW-OLD-01 → SW-NEW-02（不符合對應）"),
            ("AA:BB:CC:DD:05:05", "異常：SW-OLD-02 → SW-UNKNOWN（未知設備）"),
        ]

        for i, (mac, desc) in enumerate(mac_list):
            mac_entry = MaintenanceMacList(
                maintenance_id=maintenance_id,
                mac_address=mac,
                ip_address=f"10.0.0.{i + 1}",
                detection_status=ClientDetectionStatus.NOT_DETECTED,
            )
            session.add(mac_entry)
            print(f"   - {mac}: {desc}")

        await session.commit()
        print("   ✅ MAC 清單已建立")

    return maintenance_id


async def generate_old_phase_data(maintenance_id: str):
    """產生 OLD 階段資料"""
    from app.db.base import get_session_context
    from app.db.models import ClientRecord
    from app.core.enums import MaintenancePhase

    print("\n📋 [5] 產生 OLD 階段資料...")

    now = datetime.now(timezone.utc)

    # OLD 階段：所有 MAC 都連接到舊設備
    old_records = [
        ("AA:BB:CC:DD:01:01", "SW-OLD-01", "Gi1/0/1"),
        ("AA:BB:CC:DD:02:02", "SW-OLD-02", "Gi1/0/2"),
        ("AA:BB:CC:DD:03:03", "SW-OLD-03", "Gi1/0/3"),
        ("AA:BB:CC:DD:04:04", "SW-OLD-01", "Gi1/0/4"),  # 這個會移到錯誤的新設備
        ("AA:BB:CC:DD:05:05", "SW-OLD-02", "Gi1/0/5"),  # 這個會移到未知設備
    ]

    async with get_session_context() as session:
        for mac, switch, interface in old_records:
            record = ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.OLD,
                collected_at=now - timedelta(hours=1),  # 1 小時前
                mac_address=mac,
                ip_address=f"10.0.0.{hash(mac) % 255}",
                switch_hostname=switch,
                interface_name=interface,
                vlan_id=100,
                speed="1000",
                duplex="full",
                link_status=True,
                ping_reachable=True,
                acl_passes=True,
            )
            session.add(record)
            print(f"   - [OLD] {mac} @ {switch}/{interface}")

        await session.commit()
        print("   ✅ OLD 階段資料已產生")


async def generate_new_phase_data(maintenance_id: str):
    """產生 NEW 階段資料"""
    from app.db.base import get_session_context
    from app.db.models import ClientRecord, MaintenanceMacList
    from app.core.enums import MaintenancePhase, ClientDetectionStatus
    from sqlalchemy import update

    print("\n📋 [6] 產生 NEW 階段資料...")

    now = datetime.now(timezone.utc)

    # NEW 階段：MAC 移到新設備（部分符合對應，部分不符合）
    new_records = [
        # 正常對應
        ("AA:BB:CC:DD:01:01", "SW-NEW-01", "Gi1/0/1"),  # 符合：OLD-01 → NEW-01 ✓
        ("AA:BB:CC:DD:02:02", "SW-NEW-02", "Gi1/0/2"),  # 符合：OLD-02 → NEW-02 ✓
        ("AA:BB:CC:DD:03:03", "SW-NEW-03", "Gi1/0/3"),  # 符合：OLD-03 → NEW-03 ✓
        # 不符合對應
        ("AA:BB:CC:DD:04:04", "SW-NEW-02", "Gi1/0/4"),  # 不符合：OLD-01 應該 → NEW-01，但去了 NEW-02
        ("AA:BB:CC:DD:05:05", "SW-UNKNOWN", "Gi1/0/5"),  # 不符合：OLD-02 應該 → NEW-02，但去了未知設備
    ]

    async with get_session_context() as session:
        for mac, switch, interface in new_records:
            record = ClientRecord(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.NEW,
                collected_at=now,
                mac_address=mac,
                ip_address=f"10.0.0.{hash(mac) % 255}",
                switch_hostname=switch,
                interface_name=interface,
                vlan_id=100,
                speed="1000",
                duplex="full",
                link_status=True,
                ping_reachable=True,
                acl_passes=True,
            )
            session.add(record)
            print(f"   - [NEW] {mac} @ {switch}/{interface}")

            # 更新 detection_status
            await session.execute(
                update(MaintenanceMacList)
                .where(
                    MaintenanceMacList.maintenance_id == maintenance_id,
                    MaintenanceMacList.mac_address == mac,
                )
                .values(detection_status=ClientDetectionStatus.DETECTED)
            )

        await session.commit()
        print("   ✅ NEW 階段資料已產生")


async def run_comparison_test(maintenance_id: str):
    """執行比較測試"""
    from app.db.base import get_session_context
    from app.services.client_comparison_service import ClientComparisonService

    print("\n📋 [7] 執行比較測試...")

    comparison_service = ClientComparisonService()

    async with get_session_context() as session:
        comparisons = await comparison_service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )

        print(f"\n   比較結果 ({len(comparisons)} 筆):")
        print("   " + "-" * 70)

        expected_results = {
            "AA:BB:CC:DD:01:01": ("info", "符合對應"),
            "AA:BB:CC:DD:02:02": ("info", "符合對應"),
            "AA:BB:CC:DD:03:03": ("info", "符合對應"),
            "AA:BB:CC:DD:04:04": ("warning", "不符合對應"),
            "AA:BB:CC:DD:05:05": ("warning", "不符合對應"),
        }

        passed = 0
        failed = 0

        for comp in comparisons:
            mac = comp.mac_address
            severity = comp.severity
            is_changed = comp.is_changed

            expected_severity, desc = expected_results.get(mac, ("unknown", "未知"))

            # 檢查設備變化
            switch_change = ""
            if comp.differences and "switch_hostname" in comp.differences:
                old_sw = comp.differences["switch_hostname"].get("old", "N/A")
                new_sw = comp.differences["switch_hostname"].get("new", "N/A")
                switch_change = f"{old_sw} → {new_sw}"

            if severity == expected_severity:
                status = "✅"
                passed += 1
            else:
                status = "❌"
                failed += 1

            print(f"   {status} {mac}")
            print(f"      設備變化: {switch_change or '無'}")
            print(f"      嚴重度: {severity} (期望: {expected_severity})")
            print(f"      說明: {desc}")
            print()

        print("   " + "-" * 70)
        print(f"\n   測試結果: 通過 {passed}/{passed + failed}")

        if failed == 0:
            print("   ✅ 所有測試通過！設備對應邏輯正確運作。")
        else:
            print(f"   ❌ 有 {failed} 個測試失敗！")

        return failed == 0


async def cleanup_old_maintenance():
    """清理舊的 2026-PING-TEST 歲修"""
    from app.db.base import get_session_context
    from app.db.models import (
        MaintenanceConfig,
        MaintenanceDeviceList,
        MaintenanceMacList,
        ClientRecord,
        ClientComparison,
        ClientCategory,
        ClientCategoryMember,
        VersionRecord,
        VersionExpectation,
        CollectionBatch,
        SeverityOverride,
    )
    from sqlalchemy import delete

    old_maintenance_id = "2026-PING-TEST"

    print(f"\n📋 [0] 刪除舊的歲修 {old_maintenance_id}...")

    async with get_session_context() as session:
        # 按照外鍵依賴順序刪除
        tables_to_delete = [
            (ClientRecord, "ClientRecord"),
            (ClientComparison, "ClientComparison"),
            (VersionRecord, "VersionRecord"),
            (CollectionBatch, "CollectionBatch"),
            (SeverityOverride, "SeverityOverride"),
            (ClientCategoryMember, None),  # 需要先找到 category_ids
            (ClientCategory, "ClientCategory"),
            (VersionExpectation, "VersionExpectation"),
            (MaintenanceMacList, "MaintenanceMacList"),
            (MaintenanceDeviceList, "MaintenanceDeviceList"),
            (MaintenanceConfig, "MaintenanceConfig"),
        ]

        # 特殊處理 ClientCategoryMember（需要通過 category_id 刪除）
        from sqlalchemy import select
        cat_stmt = select(ClientCategory.id).where(
            ClientCategory.maintenance_id == old_maintenance_id
        )
        cat_result = await session.execute(cat_stmt)
        cat_ids = [row[0] for row in cat_result.fetchall()]

        if cat_ids:
            await session.execute(
                delete(ClientCategoryMember).where(
                    ClientCategoryMember.category_id.in_(cat_ids)
                )
            )
            print(f"   - ClientCategoryMember: 已刪除 (categories: {cat_ids})")

        for model, name in tables_to_delete:
            if name is None:
                continue  # 已經特殊處理
            if hasattr(model, 'maintenance_id'):
                result = await session.execute(
                    delete(model).where(model.maintenance_id == old_maintenance_id)
                )
                print(f"   - {name}: 已刪除 {result.rowcount} 筆")

        await session.commit()
        print(f"   ✅ 舊歲修 {old_maintenance_id} 已完全刪除")


async def main():
    """主程式"""
    try:
        # 0. 先刪除舊的歲修
        await cleanup_old_maintenance()

        # 1. 設定測試環境
        maintenance_id = await setup_test()

        # 2. 產生 OLD 階段資料
        await generate_old_phase_data(maintenance_id)

        # 3. 產生 NEW 階段資料
        await generate_new_phase_data(maintenance_id)

        # 4. 執行比較測試
        success = await run_comparison_test(maintenance_id)

        print("\n" + "=" * 80)
        if success:
            print("🎉 測試完成！設備對應邏輯正確運作。")
        else:
            print("⚠️ 測試完成，但有部分測試失敗。")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
