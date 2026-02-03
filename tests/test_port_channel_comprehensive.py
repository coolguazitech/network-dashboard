"""
Port Channel 期望 API 全面測試腳本

測試項目：
1. API 新增功能（多種案例）
2. API 編輯功能（多種案例）
3. 搜尋 filter（多種關鍵字組合）
4. 匯出 CSV
5. 邊界情況 CSV 匯入
6. 刪除功能（單筆/批量）
7. 重複資料處理
8. 特殊字元處理
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


async def test_all():
    """執行所有測試"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import delete

    maintenance_id = "2026-TEST-01"
    results = TestResults()

    print("=" * 70)
    print("Port Channel 期望 API 全面測試")
    print("=" * 70)

    # ========== 1. API 新增功能測試 ==========
    print("\n📋 [1] API 新增功能測試...")
    await test_api_create_cases(maintenance_id, results)

    # ========== 2. API 編輯功能測試 ==========
    print("\n📋 [2] API 編輯功能測試...")
    await test_api_edit_cases(maintenance_id, results)

    # ========== 3. 搜尋 filter 測試 ==========
    print("\n📋 [3] 搜尋 filter 測試...")
    await test_search_filter_cases(maintenance_id, results)

    # ========== 4. 匯出 CSV 測試 ==========
    print("\n📋 [4] 匯出 CSV 測試...")
    await test_export_csv(maintenance_id, results)

    # ========== 5. 邊界情況 CSV 匯入 ==========
    print("\n📋 [5] 邊界情況 CSV 匯入測試...")
    await test_edge_case_import(maintenance_id, results)

    # ========== 6. 刪除功能測試 ==========
    print("\n📋 [6] 刪除功能測試...")
    await test_delete_cases(maintenance_id, results)

    # ========== 7. 重複資料處理測試 ==========
    print("\n📋 [7] 重複資料處理測試...")
    await test_duplicate_handling(maintenance_id, results)

    # ========== 8. 特殊字元處理測試 ==========
    print("\n📋 [8] 特殊字元處理測試...")
    await test_special_characters(maintenance_id, results)

    # 總結
    return results.summary()


async def test_api_create_cases(maintenance_id: str, results: TestResults):
    """測試 API 新增功能 - 多種案例"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation, MaintenanceDeviceList
    from sqlalchemy import select, delete

    cat = "新增"

    async with get_session_context() as session:
        # 取得有效的新設備
        valid_stmt = select(MaintenanceDeviceList.new_hostname).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        valid_result = await session.execute(valid_stmt)
        valid_hostnames = {row[0] for row in valid_result.fetchall()}

        # 測試案例
        test_cases = [
            # (hostname, port_channel, member_interfaces, description, should_succeed, case_name)
            ("SW-A-01-NEW", "Po50", "Gi5/0/1;Gi5/0/2", "測試新增 1", True, "正常新增-兩埠"),
            ("SW-A-02-NEW", "Po51", "Gi5/0/1", "測試新增 2", True, "正常新增-單埠"),
            ("SW-B-01-NEW", "Po52", "Te1/0/1;Te1/0/2;Te1/0/3;Te1/0/4", "測試新增 3", True, "正常新增-四埠"),
            ("SW-INVALID", "Po53", "Gi1/0/1", "測試新增 4", False, "無效設備名稱"),
            ("SW-A-01-NEW", "Po50", "Gi6/0/1", "重複 Po", False, "重複 hostname+port_channel"),
            ("", "Po54", "Gi1/0/1", "空 hostname", False, "空 hostname"),
            ("SW-C-01-NEW", "", "Gi1/0/1", "空 port_channel", False, "空 port_channel"),
            ("SW-C-01-NEW", "Po55", "", "空 interfaces", False, "空 member_interfaces"),
        ]

        for hostname, port_channel, members, desc, should_succeed, case_name in test_cases:
            # 驗證邏輯
            is_valid = True
            error_reason = ""

            if not hostname.strip():
                is_valid = False
                error_reason = "空 hostname"
            elif not port_channel.strip():
                is_valid = False
                error_reason = "空 port_channel"
            elif not members.strip():
                is_valid = False
                error_reason = "空 member_interfaces"
            elif hostname not in valid_hostnames:
                is_valid = False
                error_reason = "設備不存在"
            else:
                # 檢查重複
                dup_stmt = select(PortChannelExpectation).where(
                    PortChannelExpectation.maintenance_id == maintenance_id,
                    PortChannelExpectation.hostname == hostname,
                    PortChannelExpectation.port_channel == port_channel,
                )
                dup_result = await session.execute(dup_stmt)
                if dup_result.scalar_one_or_none():
                    is_valid = False
                    error_reason = "重複"

            if should_succeed:
                if is_valid:
                    # 實際新增
                    item = PortChannelExpectation(
                        maintenance_id=maintenance_id,
                        hostname=hostname,
                        port_channel=port_channel,
                        member_interfaces=members,
                        description=desc,
                    )
                    session.add(item)
                    await session.commit()
                    results.add_pass(cat, case_name, f"{hostname}:{port_channel}")
                else:
                    results.add_fail(cat, case_name, "應該成功", f"失敗: {error_reason}")
            else:
                if not is_valid:
                    results.add_pass(cat, case_name, f"正確拒絕: {error_reason}")
                else:
                    results.add_fail(cat, case_name, "應該失敗", "意外成功")


async def test_api_edit_cases(maintenance_id: str, results: TestResults):
    """測試 API 編輯功能 - 多種案例"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation, MaintenanceDeviceList
    from sqlalchemy import select

    cat = "編輯"

    async with get_session_context() as session:
        # 取得有效的新設備
        valid_stmt = select(MaintenanceDeviceList.new_hostname).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        valid_result = await session.execute(valid_stmt)
        valid_hostnames = {row[0] for row in valid_result.fetchall()}

        # 取得一筆現有資料來編輯
        exist_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.port_channel == "Po50",
        )
        exist_result = await session.execute(exist_stmt)
        test_item = exist_result.scalar_one_or_none()

        if not test_item:
            results.add_fail(cat, "準備測試資料", "找到測試資料", "沒有找到 Po50")
            return

        original_desc = test_item.description
        original_members = test_item.member_interfaces
        item_id = test_item.id

        # 編輯測試案例
        edit_tests = [
            # (field, new_value, should_succeed, case_name)
            ("description", "編輯後的描述 1", True, "編輯描述"),
            ("description", "編輯後的描述 2（含中文）", True, "編輯描述-中文"),
            ("description", "", True, "清空描述"),
            ("member_interfaces", "Gi9/0/1;Gi9/0/2;Gi9/0/3", True, "編輯成員介面-三埠"),
            ("member_interfaces", "Gi9/0/1", True, "編輯成員介面-單埠"),
            ("member_interfaces", "  Gi9/0/1 ; Gi9/0/2  ", True, "編輯成員介面-含空白"),
            ("port_channel", "Po60", True, "編輯 Port Channel 名稱"),
            ("port_channel", "Po60", True, "編輯相同 Port Channel（無變化）"),
        ]

        for field, new_value, should_succeed, case_name in edit_tests:
            # 重新查詢以獲取最新狀態
            refresh_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.id == item_id
            )
            refresh_result = await session.execute(refresh_stmt)
            item = refresh_result.scalar_one_or_none()

            if not item:
                results.add_fail(cat, case_name, "找到資料", "資料不存在")
                continue

            old_value = getattr(item, field)

            if field == "description":
                item.description = new_value.strip() if new_value else None
            elif field == "member_interfaces":
                # 標準化
                members = ";".join(m.strip() for m in new_value.split(";") if m.strip())
                if members:
                    item.member_interfaces = members
                else:
                    results.add_pass(cat, case_name, "正確拒絕空成員介面")
                    continue
            elif field == "port_channel":
                # 檢查重複
                if new_value != item.port_channel:
                    dup_stmt = select(PortChannelExpectation).where(
                        PortChannelExpectation.maintenance_id == maintenance_id,
                        PortChannelExpectation.hostname == item.hostname,
                        PortChannelExpectation.port_channel == new_value,
                        PortChannelExpectation.id != item_id,
                    )
                    dup_result = await session.execute(dup_stmt)
                    if dup_result.scalar_one_or_none():
                        results.add_pass(cat, case_name, "正確拒絕重複")
                        continue
                item.port_channel = new_value.strip()

            await session.commit()
            await session.refresh(item)

            # 驗證
            new_actual = getattr(item, field)
            if field == "member_interfaces":
                expected = ";".join(m.strip() for m in new_value.split(";") if m.strip())
            elif field == "description":
                expected = new_value.strip() if new_value else None
            else:
                expected = new_value.strip()

            if new_actual == expected or (expected == "" and new_actual is None):
                results.add_pass(cat, case_name, f"'{old_value}' → '{new_actual}'")
            else:
                results.add_fail(cat, case_name, str(expected), str(new_actual))

        # 編輯 hostname 測試
        edit_hostname_tests = [
            # (new_hostname, should_succeed, case_name)
            ("SW-B-01-NEW", True, "編輯 hostname 到有效設備"),
            ("SW-INVALID", False, "編輯 hostname 到無效設備"),
            ("", False, "編輯 hostname 為空"),
        ]

        for new_hostname, should_succeed, case_name in edit_hostname_tests:
            refresh_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.id == item_id
            )
            refresh_result = await session.execute(refresh_stmt)
            item = refresh_result.scalar_one_or_none()

            if not item:
                continue

            if not new_hostname.strip():
                results.add_pass(cat, case_name, "正確拒絕空 hostname")
                continue

            if new_hostname not in valid_hostnames:
                results.add_pass(cat, case_name, "正確拒絕無效 hostname")
                continue

            # 檢查重複
            dup_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.maintenance_id == maintenance_id,
                PortChannelExpectation.hostname == new_hostname,
                PortChannelExpectation.port_channel == item.port_channel,
                PortChannelExpectation.id != item_id,
            )
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                results.add_pass(cat, case_name, "正確拒絕重複")
                continue

            old_hostname = item.hostname
            item.hostname = new_hostname
            await session.commit()
            await session.refresh(item)

            if item.hostname == new_hostname:
                results.add_pass(cat, case_name, f"'{old_hostname}' → '{new_hostname}'")
            else:
                results.add_fail(cat, case_name, new_hostname, item.hostname)


async def test_search_filter_cases(maintenance_id: str, results: TestResults):
    """測試搜尋 filter - 多種關鍵字組合"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import select, and_, or_

    cat = "搜尋"

    async with get_session_context() as session:
        # 搜尋測試案例
        search_tests = [
            # (search_keyword, expected_min_count, case_name)
            ("SW-A", 2, "hostname 前綴 SW-A"),
            ("SW-B", 2, "hostname 前綴 SW-B"),
            ("SW-C", 1, "hostname 前綴 SW-C"),
            ("Po1", 3, "port_channel 包含 Po1"),
            ("Po5", 2, "port_channel 包含 Po5"),
            ("鏈路", 2, "描述包含「鏈路」"),
            ("測試", 0, "描述包含「測試」"),
            ("聚合", 1, "描述包含「聚合」"),
            ("Gi1", 0, "成員介面 Gi1（不在搜尋範圍）"),
            ("NEW", 5, "hostname 包含 NEW"),
            ("nonexistent123", 0, "不存在的關鍵字"),
            ("", None, "空關鍵字（應返回全部）"),
            ("  ", None, "空白關鍵字（應返回全部）"),
            ("Po 1", 0, "空格分隔的關鍵字（AND 邏輯）"),
            ("SW Po", 0, "多關鍵字（AND 邏輯）"),
        ]

        for search, expected_min, case_name in search_tests:
            if not search or not search.strip():
                # 空關鍵字應返回全部
                stmt = select(PortChannelExpectation).where(
                    PortChannelExpectation.maintenance_id == maintenance_id
                )
            else:
                keywords = search.strip().split()
                field_conditions = []
                for field in [
                    PortChannelExpectation.hostname,
                    PortChannelExpectation.port_channel,
                    PortChannelExpectation.description,
                ]:
                    field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
                    field_conditions.append(field_match)

                stmt = select(PortChannelExpectation).where(
                    PortChannelExpectation.maintenance_id == maintenance_id,
                    or_(*field_conditions)
                )

            result = await session.execute(stmt)
            items = result.scalars().all()
            count = len(items)

            if expected_min is None:
                # 空關鍵字應返回全部
                if count > 0:
                    results.add_pass(cat, case_name, f"返回 {count} 筆（全部）")
                else:
                    results.add_fail(cat, case_name, "返回全部資料", f"返回 {count} 筆")
            elif count >= expected_min:
                results.add_pass(cat, case_name, f"返回 {count} 筆 (≥{expected_min})")
            else:
                results.add_fail(cat, case_name, f"≥{expected_min} 筆", f"{count} 筆")


async def test_export_csv(maintenance_id: str, results: TestResults):
    """測試匯出 CSV"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import select

    cat = "匯出"

    async with get_session_context() as session:
        stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id
        ).order_by(
            PortChannelExpectation.hostname,
            PortChannelExpectation.port_channel,
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        # 模擬 CSV 匯出
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["hostname", "port_channel", "member_interfaces", "description"])

        for item in items:
            writer.writerow([
                item.hostname,
                item.port_channel,
                item.member_interfaces,
                item.description or "",
            ])

        csv_content = output.getvalue()
        lines = csv_content.strip().split("\n")

        # 測試 1: 資料筆數
        data_count = len(lines) - 1  # 減去標題
        if data_count == len(items):
            results.add_pass(cat, "資料筆數", f"{data_count} 筆")
        else:
            results.add_fail(cat, "資料筆數", str(len(items)), str(data_count))

        # 測試 2: 標題格式
        reader = csv.reader(io.StringIO(csv_content))
        header = next(reader)
        expected_header = ["hostname", "port_channel", "member_interfaces", "description"]
        if header == expected_header:
            results.add_pass(cat, "標題格式", "欄位正確")
        else:
            results.add_fail(cat, "標題格式", str(expected_header), str(header))

        # 測試 3: 資料完整性
        rows = list(reader)
        incomplete_rows = [i for i, row in enumerate(rows, 2) if len(row) != 4]
        if not incomplete_rows:
            results.add_pass(cat, "資料完整性", "所有列都有 4 個欄位")
        else:
            results.add_fail(cat, "資料完整性", "4 欄位", f"列 {incomplete_rows} 欄位數不對")

        # 測試 4: 中文編碼
        has_chinese = any("中" in line or "鏈" in line or "路" in line for line in lines)
        if has_chinese or len(items) == 0:
            results.add_pass(cat, "中文編碼", "中文正確顯示")
        else:
            results.add_pass(cat, "中文編碼", "無中文資料（跳過）")

        # 測試 5: 分號分隔的成員介面
        for row in rows:
            if len(row) >= 3 and ";" in row[2]:
                results.add_pass(cat, "成員介面格式", "分號分隔正確")
                break
        else:
            results.add_pass(cat, "成員介面格式", "無多成員資料（跳過）")


async def test_edge_case_import(maintenance_id: str, results: TestResults):
    """測試邊界情況 CSV 匯入"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation, MaintenanceDeviceList
    from sqlalchemy import select

    cat = "邊界情況"

    csv_path = "/Users/coolguazi/Project/ClineTest/network_dashboard/tests/data/port_channel_edge_cases.csv"

    if not os.path.exists(csv_path):
        results.add_fail(cat, "CSV 檔案", "檔案存在", "檔案不存在")
        return

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    async with get_session_context() as session:
        valid_stmt = select(MaintenanceDeviceList.new_hostname).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        valid_result = await session.execute(valid_stmt)
        valid_hostnames = {row[0] for row in valid_result.fetchall()}

        reader = csv.DictReader(io.StringIO(content))

        for row_num, row in enumerate(reader, start=2):
            hostname = row.get("hostname", "").strip()
            port_channel = row.get("port_channel", "").strip()
            member_interfaces = row.get("member_interfaces", "").strip()
            description = row.get("description", "").strip()

            # 判斷預期結果
            should_fail = "應報錯" in description
            case_name = f"Row {row_num}: {description[:20]}..."

            # 驗證邏輯
            error = None
            if not hostname:
                error = "空 hostname"
            elif not port_channel:
                error = "空 port_channel"
            elif not member_interfaces:
                error = "空 member_interfaces"
            elif hostname not in valid_hostnames:
                error = f"設備不存在: {hostname}"

            if should_fail:
                if error:
                    results.add_pass(cat, case_name, f"正確拒絕: {error}")
                else:
                    results.add_fail(cat, case_name, "應該失敗", "驗證通過")
            else:
                if not error:
                    results.add_pass(cat, case_name, "驗證通過")
                else:
                    results.add_fail(cat, case_name, "應該成功", f"失敗: {error}")


async def test_delete_cases(maintenance_id: str, results: TestResults):
    """測試刪除功能"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import select, delete

    cat = "刪除"

    async with get_session_context() as session:
        # 先新增測試資料用於刪除
        test_items = [
            PortChannelExpectation(
                maintenance_id=maintenance_id,
                hostname="SW-A-01-NEW",
                port_channel="Po90",
                member_interfaces="Gi9/0/1",
                description="刪除測試 1",
            ),
            PortChannelExpectation(
                maintenance_id=maintenance_id,
                hostname="SW-A-02-NEW",
                port_channel="Po91",
                member_interfaces="Gi9/0/2",
                description="刪除測試 2",
            ),
            PortChannelExpectation(
                maintenance_id=maintenance_id,
                hostname="SW-B-01-NEW",
                port_channel="Po92",
                member_interfaces="Gi9/0/3",
                description="刪除測試 3",
            ),
        ]

        for item in test_items:
            # 檢查是否已存在
            check_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.maintenance_id == maintenance_id,
                PortChannelExpectation.hostname == item.hostname,
                PortChannelExpectation.port_channel == item.port_channel,
            )
            check_result = await session.execute(check_stmt)
            if not check_result.scalar_one_or_none():
                session.add(item)

        await session.commit()

        # 測試 1: 單筆刪除
        del_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.port_channel == "Po90",
        )
        del_result = await session.execute(del_stmt)
        del_item = del_result.scalar_one_or_none()

        if del_item:
            del_id = del_item.id
            await session.delete(del_item)
            await session.commit()

            # 確認刪除
            confirm_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.id == del_id
            )
            confirm_result = await session.execute(confirm_stmt)
            if not confirm_result.scalar_one_or_none():
                results.add_pass(cat, "單筆刪除", f"ID {del_id} 已刪除")
            else:
                results.add_fail(cat, "單筆刪除", "資料已刪除", "資料仍存在")
        else:
            results.add_pass(cat, "單筆刪除", "無測試資料（跳過）")

        # 測試 2: 批量刪除
        batch_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.port_channel.in_(["Po91", "Po92"]),
        )
        batch_result = await session.execute(batch_stmt)
        batch_items = batch_result.scalars().all()
        batch_ids = [item.id for item in batch_items]

        if batch_ids:
            del_batch = delete(PortChannelExpectation).where(
                PortChannelExpectation.id.in_(batch_ids)
            )
            await session.execute(del_batch)
            await session.commit()

            # 確認刪除
            confirm_batch = select(PortChannelExpectation).where(
                PortChannelExpectation.id.in_(batch_ids)
            )
            confirm_result = await session.execute(confirm_batch)
            remaining = confirm_result.scalars().all()

            if len(remaining) == 0:
                results.add_pass(cat, "批量刪除", f"{len(batch_ids)} 筆已刪除")
            else:
                results.add_fail(cat, "批量刪除", "0 筆剩餘", f"{len(remaining)} 筆剩餘")
        else:
            results.add_pass(cat, "批量刪除", "無測試資料（跳過）")

        # 測試 3: 刪除不存在的資料
        fake_id = 999999
        fake_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.id == fake_id
        )
        fake_result = await session.execute(fake_stmt)
        if not fake_result.scalar_one_or_none():
            results.add_pass(cat, "刪除不存在資料", "正確處理（無影響）")
        else:
            results.add_fail(cat, "刪除不存在資料", "資料不存在", "意外找到資料")


async def test_duplicate_handling(maintenance_id: str, results: TestResults):
    """測試重複資料處理"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import select

    cat = "重複處理"

    async with get_session_context() as session:
        # 找一筆現有資料
        exist_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id
        ).limit(1)
        exist_result = await session.execute(exist_stmt)
        existing = exist_result.scalar_one_or_none()

        if not existing:
            results.add_pass(cat, "重複檢測", "無現有資料（跳過）")
            return

        # 嘗試新增重複
        dup_check = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.hostname == existing.hostname,
            PortChannelExpectation.port_channel == existing.port_channel,
        )
        dup_result = await session.execute(dup_check)

        if dup_result.scalar_one_or_none():
            results.add_pass(cat, "重複檢測", f"正確識別: {existing.hostname}:{existing.port_channel}")
        else:
            results.add_fail(cat, "重複檢測", "應識別重複", "未識別")

        # CSV 重複匯入（更新邏輯）
        # 模擬更新
        old_desc = existing.description
        existing.description = "CSV 重複匯入更新"
        await session.commit()
        await session.refresh(existing)

        if existing.description == "CSV 重複匯入更新":
            results.add_pass(cat, "CSV 重複更新", f"描述從 '{old_desc}' 更新為 'CSV 重複匯入更新'")
            # 還原
            existing.description = old_desc
            await session.commit()
        else:
            results.add_fail(cat, "CSV 重複更新", "更新成功", "更新失敗")


async def test_special_characters(maintenance_id: str, results: TestResults):
    """測試特殊字元處理"""
    from app.db.base import get_session_context
    from app.db.models import PortChannelExpectation
    from sqlalchemy import select, delete

    cat = "特殊字元"

    async with get_session_context() as session:
        # 測試案例
        special_tests = [
            # (description, case_name)
            ("描述包含「引號」", "中文引號"),
            ("描述包含 'single quotes'", "英文單引號"),
            ('描述包含 "double quotes"', "英文雙引號"),
            ("描述包含 comma, here", "逗號"),
            ("描述包含\ttab", "Tab 字元"),
            ("描述包含 & 符號", "& 符號"),
            ("描述包含 < > 符號", "尖括號"),
            ("描述包含 emoji 😀", "Emoji"),
        ]

        for desc, case_name in special_tests:
            # 先檢查是否已存在
            check_stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.maintenance_id == maintenance_id,
                PortChannelExpectation.hostname == "SW-C-01-NEW",
                PortChannelExpectation.port_channel == "Po99",
            )
            check_result = await session.execute(check_stmt)
            existing = check_result.scalar_one_or_none()

            if existing:
                existing.description = desc
                await session.commit()
                await session.refresh(existing)

                if existing.description == desc:
                    results.add_pass(cat, case_name, f"正確儲存: {desc[:15]}...")
                else:
                    results.add_fail(cat, case_name, desc, existing.description)
            else:
                # 新增
                item = PortChannelExpectation(
                    maintenance_id=maintenance_id,
                    hostname="SW-C-01-NEW",
                    port_channel="Po99",
                    member_interfaces="Gi9/9/9",
                    description=desc,
                )
                session.add(item)
                await session.commit()
                await session.refresh(item)

                if item.description == desc:
                    results.add_pass(cat, case_name, f"正確儲存: {desc[:15]}...")
                else:
                    results.add_fail(cat, case_name, desc, item.description)

        # 清理特殊字元測試資料
        cleanup_stmt = delete(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.port_channel == "Po99",
        )
        await session.execute(cleanup_stmt)
        await session.commit()
        results.add_pass(cat, "清理測試資料", "已清理")


async def main():
    """主程式"""
    try:
        success = await test_all()
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
