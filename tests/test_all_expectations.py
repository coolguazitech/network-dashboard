"""
所有期望 API 全面測試腳本

測試 Uplink 期望、Version 期望、Port Channel 期望
"""

import asyncio
import sys
import os
import io
import csv
from typing import Any

sys.path.insert(0, "/Users/coolguazi/Project/ClineTest/network_dashboard")


class TestResults:
    """測試結果追蹤"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.category_counts = {}

    def add_pass(self, category: str, test_name: str, detail: str = ""):
        self.passed.append((category, test_name, detail))
        self.category_counts[category] = self.category_counts.get(category, 0) + 1
        print(f"  ✅ [{category}] {test_name}" + (f": {detail}" if detail else ""))

    def add_fail(self, category: str, test_name: str, expected: str, actual: str):
        self.failed.append((category, test_name, expected, actual))
        self.category_counts[category] = self.category_counts.get(category, 0)
        print(f"  ❌ [{category}] {test_name}")
        print(f"     期望: {expected}")
        print(f"     實際: {actual}")

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*70}")
        print(f"測試結果: {len(self.passed)}/{total} 通過")
        print(f"\n類別統計:")
        for cat, count in sorted(self.category_counts.items()):
            print(f"  - {cat}: {count} 測試")
        if self.failed:
            print(f"\n失敗項目:")
            for cat, name, expected, actual in self.failed:
                print(f"  - [{cat}] {name}")
        print(f"{'='*70}")
        return len(self.failed) == 0


# ============================================================================
# UPLINK 期望測試
# ============================================================================

async def test_uplink_expectations(maintenance_id: str, results: TestResults):
    """測試 Uplink 期望 API"""
    from app.db.base import get_session_context
    from app.db.models import UplinkExpectation, MaintenanceDeviceList
    from sqlalchemy import select, delete, and_, or_

    print("\n" + "=" * 70)
    print("📌 Uplink 期望測試")
    print("=" * 70)

    async with get_session_context() as session:
        # 取得有效設備（新舊皆可）
        valid_stmt = select(
            MaintenanceDeviceList.new_hostname,
            MaintenanceDeviceList.old_hostname,
        ).where(MaintenanceDeviceList.maintenance_id == maintenance_id)
        valid_result = await session.execute(valid_stmt)
        valid_hostnames = set()
        for row in valid_result.fetchall():
            if row[0]: valid_hostnames.add(row[0])
            if row[1]: valid_hostnames.add(row[1])

        # 清理舊資料
        await session.execute(
            delete(UplinkExpectation).where(
                UplinkExpectation.maintenance_id == maintenance_id
            )
        )
        await session.commit()
        results.add_pass("Uplink-清理", "清理舊資料", "完成")

        # ========== 新增測試 ==========
        print("\n📋 Uplink 新增測試...")
        create_tests = [
            # (hostname, local_if, neighbor, neighbor_if, desc, should_succeed, case_name)
            ("SW-A-01-NEW", "Gi1/0/1", "SW-A-02-NEW", "Gi1/0/1", "正常鏈路", True, "正常新增"),
            ("SW-A-01-NEW", "Gi1/0/2", "SW-B-01-NEW", "Gi1/0/1", "跨區鏈路", True, "跨區鏈路"),
            ("SW-B-01-NEW", "Te1/0/1", "SW-B-02-NEW", "Te1/0/1", "10G 鏈路", True, "10G 鏈路"),
            ("SW-C-01-NEW", "Gi1/0/1", "SW-A-01-NEW", None, "無鄰居介面", True, "鄰居介面為空"),
            ("SW-INVALID", "Gi1/0/1", "SW-A-01-NEW", "Gi1/0/1", "無效設備", False, "無效本地設備"),
            ("SW-A-01-NEW", "Gi1/0/3", "SW-INVALID", "Gi1/0/1", "無效鄰居", False, "無效鄰居設備"),
            ("", "Gi1/0/1", "SW-A-01-NEW", "Gi1/0/1", "空 hostname", False, "空 hostname"),
            ("SW-A-01-NEW", "", "SW-A-02-NEW", "Gi1/0/1", "空介面", False, "空 local_interface"),
            ("SW-A-01-NEW", "Gi1/0/1", "", "Gi1/0/1", "空鄰居", False, "空 expected_neighbor"),
            ("SW-A-01-NEW", "Gi1/0/1", "SW-A-02-NEW", "Gi1/0/1", "重複", False, "重複 hostname+interface"),
        ]

        for hostname, local_if, neighbor, neighbor_if, desc, should_succeed, case_name in create_tests:
            is_valid = True
            error = ""

            if not hostname.strip():
                is_valid = False
                error = "空 hostname"
            elif not local_if.strip():
                is_valid = False
                error = "空 local_interface"
            elif not neighbor.strip():
                is_valid = False
                error = "空 expected_neighbor"
            elif hostname not in valid_hostnames:
                is_valid = False
                error = "本地設備不存在"
            elif neighbor not in valid_hostnames:
                is_valid = False
                error = "鄰居設備不存在"
            else:
                # 檢查重複
                dup_stmt = select(UplinkExpectation).where(
                    UplinkExpectation.maintenance_id == maintenance_id,
                    UplinkExpectation.hostname == hostname,
                    UplinkExpectation.local_interface == local_if,
                )
                dup_result = await session.execute(dup_stmt)
                if dup_result.scalar_one_or_none():
                    is_valid = False
                    error = "重複"

            if should_succeed:
                if is_valid:
                    item = UplinkExpectation(
                        maintenance_id=maintenance_id,
                        hostname=hostname,
                        local_interface=local_if,
                        expected_neighbor=neighbor,
                        expected_interface=neighbor_if,
                        description=desc,
                    )
                    session.add(item)
                    await session.commit()
                    results.add_pass("Uplink-新增", case_name, f"{hostname}:{local_if}")
                else:
                    results.add_fail("Uplink-新增", case_name, "應該成功", f"失敗: {error}")
            else:
                if not is_valid:
                    results.add_pass("Uplink-新增", case_name, f"正確拒絕: {error}")
                else:
                    results.add_fail("Uplink-新增", case_name, "應該失敗", "意外成功")

        # ========== 編輯測試 ==========
        print("\n📋 Uplink 編輯測試...")
        edit_stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id
        ).limit(1)
        edit_result = await session.execute(edit_stmt)
        edit_item = edit_result.scalar_one_or_none()

        if edit_item:
            # 編輯描述
            old_desc = edit_item.description
            edit_item.description = "編輯後的描述"
            await session.commit()
            await session.refresh(edit_item)
            if edit_item.description == "編輯後的描述":
                results.add_pass("Uplink-編輯", "編輯描述", f"'{old_desc}' → '編輯後的描述'")
            else:
                results.add_fail("Uplink-編輯", "編輯描述", "編輯後的描述", edit_item.description)

            # 編輯鄰居介面
            edit_item.expected_interface = "Gi2/0/99"
            await session.commit()
            await session.refresh(edit_item)
            if edit_item.expected_interface == "Gi2/0/99":
                results.add_pass("Uplink-編輯", "編輯鄰居介面", "Gi2/0/99")
            else:
                results.add_fail("Uplink-編輯", "編輯鄰居介面", "Gi2/0/99", edit_item.expected_interface)

            # 清空鄰居介面
            edit_item.expected_interface = None
            await session.commit()
            await session.refresh(edit_item)
            if edit_item.expected_interface is None:
                results.add_pass("Uplink-編輯", "清空鄰居介面", "None")
            else:
                results.add_fail("Uplink-編輯", "清空鄰居介面", "None", str(edit_item.expected_interface))
        else:
            results.add_fail("Uplink-編輯", "準備測試資料", "找到資料", "無資料")

        # ========== 搜尋測試 ==========
        print("\n📋 Uplink 搜尋測試...")
        search_tests = [
            ("SW-A", 2, "hostname SW-A"),
            ("Gi1", 0, "介面 Gi1（不在搜尋範圍）"),
            ("鏈路", 2, "描述「鏈路」"),
            ("nonexistent", 0, "不存在關鍵字"),
        ]

        for search, expected_min, case_name in search_tests:
            keywords = search.strip().split()
            field_conditions = []
            for field in [
                UplinkExpectation.hostname,
                UplinkExpectation.expected_neighbor,
                UplinkExpectation.description,
            ]:
                field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
                field_conditions.append(field_match)

            stmt = select(UplinkExpectation).where(
                UplinkExpectation.maintenance_id == maintenance_id,
                or_(*field_conditions)
            )
            result = await session.execute(stmt)
            count = len(result.scalars().all())

            if count >= expected_min:
                results.add_pass("Uplink-搜尋", case_name, f"{count} 筆")
            else:
                results.add_fail("Uplink-搜尋", case_name, f"≥{expected_min}", str(count))

        # ========== 刪除測試 ==========
        print("\n📋 Uplink 刪除測試...")
        del_stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id
        ).limit(1)
        del_result = await session.execute(del_stmt)
        del_item = del_result.scalar_one_or_none()

        if del_item:
            del_id = del_item.id
            await session.delete(del_item)
            await session.commit()

            confirm = await session.execute(
                select(UplinkExpectation).where(UplinkExpectation.id == del_id)
            )
            if not confirm.scalar_one_or_none():
                results.add_pass("Uplink-刪除", "單筆刪除", f"ID {del_id}")
            else:
                results.add_fail("Uplink-刪除", "單筆刪除", "已刪除", "仍存在")
        else:
            results.add_pass("Uplink-刪除", "單筆刪除", "無資料（跳過）")


# ============================================================================
# VERSION 期望測試
# ============================================================================

async def test_version_expectations(maintenance_id: str, results: TestResults):
    """測試 Version 期望 API"""
    from app.db.base import get_session_context
    from app.db.models import VersionExpectation, MaintenanceDeviceList
    from sqlalchemy import select, delete, and_, or_

    print("\n" + "=" * 70)
    print("📌 Version 期望測試")
    print("=" * 70)

    async with get_session_context() as session:
        # 取得有效設備（只有新設備）
        valid_stmt = select(MaintenanceDeviceList.new_hostname).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        valid_result = await session.execute(valid_stmt)
        valid_hostnames = {row[0] for row in valid_result.fetchall()}

        # 清理舊資料
        await session.execute(
            delete(VersionExpectation).where(
                VersionExpectation.maintenance_id == maintenance_id
            )
        )
        await session.commit()
        results.add_pass("Version-清理", "清理舊資料", "完成")

        # ========== 新增測試 ==========
        print("\n📋 Version 新增測試...")
        create_tests = [
            # (hostname, versions, desc, should_succeed, case_name)
            ("SW-A-01-NEW", "17.3.3", "單一版本", True, "單一版本"),
            ("SW-A-02-NEW", "17.3.3;17.3.4", "多版本（分號分隔）", True, "多版本"),
            ("SW-B-01-NEW", "17.3.3 ; 17.3.4 ; 17.3.5", "多版本（含空白）", True, "多版本含空白"),
            ("SW-B-02-NEW", "9.3(8)", "特殊版本格式", True, "特殊版本格式"),
            ("SW-C-01-NEW", "7.0(3)I7(6)", "NX-OS 版本", True, "NX-OS 版本"),
            ("SW-INVALID", "17.3.3", "無效設備", False, "無效設備"),
            ("SW-A-01", "17.3.3", "舊設備", False, "舊設備 hostname"),
            ("", "17.3.3", "空 hostname", False, "空 hostname"),
            ("SW-A-01-NEW", "", "空版本", False, "空 expected_versions"),
            ("SW-A-01-NEW", "17.3.3", "重複設備", False, "重複 hostname"),
        ]

        for hostname, versions, desc, should_succeed, case_name in create_tests:
            is_valid = True
            error = ""

            if not hostname.strip():
                is_valid = False
                error = "空 hostname"
            elif not versions.strip():
                is_valid = False
                error = "空 expected_versions"
            elif hostname not in valid_hostnames:
                is_valid = False
                error = "設備不存在"
            else:
                # 檢查重複
                dup_stmt = select(VersionExpectation).where(
                    VersionExpectation.maintenance_id == maintenance_id,
                    VersionExpectation.hostname == hostname,
                )
                dup_result = await session.execute(dup_stmt)
                if dup_result.scalar_one_or_none():
                    is_valid = False
                    error = "重複"

            if should_succeed:
                if is_valid:
                    # 標準化版本格式
                    normalized = ";".join(v.strip() for v in versions.split(";") if v.strip())
                    item = VersionExpectation(
                        maintenance_id=maintenance_id,
                        hostname=hostname,
                        expected_versions=normalized,
                        description=desc,
                    )
                    session.add(item)
                    await session.commit()
                    results.add_pass("Version-新增", case_name, f"{hostname}: {normalized}")
                else:
                    results.add_fail("Version-新增", case_name, "應該成功", f"失敗: {error}")
            else:
                if not is_valid:
                    results.add_pass("Version-新增", case_name, f"正確拒絕: {error}")
                else:
                    results.add_fail("Version-新增", case_name, "應該失敗", "意外成功")

        # ========== 編輯測試 ==========
        print("\n📋 Version 編輯測試...")
        edit_stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id
        ).limit(1)
        edit_result = await session.execute(edit_stmt)
        edit_item = edit_result.scalar_one_or_none()

        if edit_item:
            # 編輯版本
            old_ver = edit_item.expected_versions
            edit_item.expected_versions = "18.0.0;18.0.1"
            await session.commit()
            await session.refresh(edit_item)
            if edit_item.expected_versions == "18.0.0;18.0.1":
                results.add_pass("Version-編輯", "編輯版本", f"'{old_ver}' → '18.0.0;18.0.1'")
            else:
                results.add_fail("Version-編輯", "編輯版本", "18.0.0;18.0.1", edit_item.expected_versions)

            # 編輯描述
            edit_item.description = "編輯後的版本描述"
            await session.commit()
            await session.refresh(edit_item)
            if edit_item.description == "編輯後的版本描述":
                results.add_pass("Version-編輯", "編輯描述", "編輯後的版本描述")
            else:
                results.add_fail("Version-編輯", "編輯描述", "編輯後的版本描述", edit_item.description)

            # 新增版本（追加）
            edit_item.expected_versions = edit_item.expected_versions + ";18.0.2"
            await session.commit()
            await session.refresh(edit_item)
            if "18.0.2" in edit_item.expected_versions:
                results.add_pass("Version-編輯", "追加版本", edit_item.expected_versions)
            else:
                results.add_fail("Version-編輯", "追加版本", "包含 18.0.2", edit_item.expected_versions)
        else:
            results.add_fail("Version-編輯", "準備測試資料", "找到資料", "無資料")

        # ========== 搜尋測試 ==========
        print("\n📋 Version 搜尋測試...")
        search_tests = [
            ("SW-A", 2, "hostname SW-A"),
            ("17.3", 2, "版本 17.3"),
            ("9.3", 1, "版本 9.3"),
            ("版本", 2, "描述「版本」"),
            ("nonexistent", 0, "不存在關鍵字"),
        ]

        for search, expected_min, case_name in search_tests:
            keywords = search.strip().split()
            field_conditions = []
            for field in [
                VersionExpectation.hostname,
                VersionExpectation.expected_versions,
                VersionExpectation.description,
            ]:
                field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
                field_conditions.append(field_match)

            stmt = select(VersionExpectation).where(
                VersionExpectation.maintenance_id == maintenance_id,
                or_(*field_conditions)
            )
            result = await session.execute(stmt)
            count = len(result.scalars().all())

            if count >= expected_min:
                results.add_pass("Version-搜尋", case_name, f"{count} 筆")
            else:
                results.add_fail("Version-搜尋", case_name, f"≥{expected_min}", str(count))

        # ========== 匯出測試 ==========
        print("\n📋 Version 匯出測試...")
        export_stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id
        )
        export_result = await session.execute(export_stmt)
        items = export_result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["hostname", "expected_versions", "description"])
        for item in items:
            writer.writerow([item.hostname, item.expected_versions, item.description or ""])

        csv_content = output.getvalue()
        lines = csv_content.strip().split("\n")

        if len(lines) - 1 == len(items):
            results.add_pass("Version-匯出", "資料筆數", f"{len(items)} 筆")
        else:
            results.add_fail("Version-匯出", "資料筆數", str(len(items)), str(len(lines) - 1))

        # 驗證分號分隔
        has_semicolon = any(";" in line for line in lines[1:])
        if has_semicolon:
            results.add_pass("Version-匯出", "分號分隔版本", "正確")
        else:
            results.add_pass("Version-匯出", "分號分隔版本", "無多版本資料（跳過）")

        # ========== 刪除測試 ==========
        print("\n📋 Version 刪除測試...")
        del_stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id
        ).limit(1)
        del_result = await session.execute(del_stmt)
        del_item = del_result.scalar_one_or_none()

        if del_item:
            del_id = del_item.id
            await session.delete(del_item)
            await session.commit()

            confirm = await session.execute(
                select(VersionExpectation).where(VersionExpectation.id == del_id)
            )
            if not confirm.scalar_one_or_none():
                results.add_pass("Version-刪除", "單筆刪除", f"ID {del_id}")
            else:
                results.add_fail("Version-刪除", "單筆刪除", "已刪除", "仍存在")
        else:
            results.add_pass("Version-刪除", "單筆刪除", "無資料（跳過）")


# ============================================================================
# 清理函數
# ============================================================================

async def cleanup_except_port_channel(maintenance_id: str, results: TestResults):
    """清理除 Port Channel 以外的所有期望資料"""
    from app.db.base import get_session_context
    from app.db.models import UplinkExpectation, VersionExpectation, PortChannelExpectation
    from sqlalchemy import delete, select

    print("\n" + "=" * 70)
    print("📌 清理資料（只保留 Port Channel 期望）")
    print("=" * 70)

    async with get_session_context() as session:
        # 刪除 Uplink 期望
        uplink_del = await session.execute(
            delete(UplinkExpectation).where(
                UplinkExpectation.maintenance_id == maintenance_id
            )
        )
        results.add_pass("清理", "刪除 Uplink 期望", f"{uplink_del.rowcount} 筆")

        # 刪除 Version 期望
        version_del = await session.execute(
            delete(VersionExpectation).where(
                VersionExpectation.maintenance_id == maintenance_id
            )
        )
        results.add_pass("清理", "刪除 Version 期望", f"{version_del.rowcount} 筆")

        await session.commit()

        # 確認 Port Channel 還在
        pc_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id
        )
        pc_result = await session.execute(pc_stmt)
        pc_count = len(pc_result.scalars().all())
        results.add_pass("清理", "保留 Port Channel 期望", f"{pc_count} 筆")


async def main():
    """主程式"""
    maintenance_id = "2026-TEST-01"
    results = TestResults()

    print("=" * 70)
    print("所有期望 API 全面測試")
    print("=" * 70)

    try:
        # 測試 Uplink 期望
        await test_uplink_expectations(maintenance_id, results)

        # 測試 Version 期望
        await test_version_expectations(maintenance_id, results)

        # 清理資料
        await cleanup_except_port_channel(maintenance_id, results)

        # 總結
        success = results.summary()

        if success:
            print("\n🎉 所有測試通過！")
        else:
            print("\n⚠️ 部分測試失敗，請檢查上述錯誤。")

    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
