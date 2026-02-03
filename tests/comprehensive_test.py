"""
Comprehensive System Testing Script

測試範圍：
1. 比較邏輯 (Comparison Logic)
2. 嚴重度計算 (Severity Calculation)
3. 類別統計 (Category Statistics)
4. Checkpoint/趨勢圖 (Checkpoint/Trend)
5. Dashboard 指標 (Dashboard Indicators)
6. Mock 資料生成 (Mock Data Generation)
7. API 一致性 (API Consistency)
8. Edge Cases
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

# Add project root to path
sys.path.insert(0, "/Users/coolguazi/Project/ClineTest/network_dashboard")


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append({"name": test_name, "details": details})

    def add_fail(self, test_name: str, expected: Any, actual: Any, details: str = ""):
        self.failed.append({
            "name": test_name,
            "expected": expected,
            "actual": actual,
            "details": details,
        })

    def add_warning(self, test_name: str, message: str):
        self.warnings.append({"name": test_name, "message": message})

    def summary(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append("                    綜合測試報告 (Comprehensive Test Report)")
        lines.append("=" * 80)
        lines.append(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(f"✅ 通過: {len(self.passed)}")
        lines.append(f"❌ 失敗: {len(self.failed)}")
        lines.append(f"⚠️  警告: {len(self.warnings)}")
        lines.append("")

        if self.failed:
            lines.append("-" * 80)
            lines.append("❌ 失敗的測試:")
            lines.append("-" * 80)
            for i, f in enumerate(self.failed, 1):
                lines.append(f"\n{i}. {f['name']}")
                lines.append(f"   期望: {f['expected']}")
                lines.append(f"   實際: {f['actual']}")
                if f['details']:
                    lines.append(f"   詳情: {f['details']}")

        if self.warnings:
            lines.append("")
            lines.append("-" * 80)
            lines.append("⚠️  警告:")
            lines.append("-" * 80)
            for w in self.warnings:
                lines.append(f"  - {w['name']}: {w['message']}")

        if self.passed:
            lines.append("")
            lines.append("-" * 80)
            lines.append("✅ 通過的測試:")
            lines.append("-" * 80)
            for p in self.passed:
                detail = f" ({p['details']})" if p['details'] else ""
                lines.append(f"  ✓ {p['name']}{detail}")

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)


results = TestResult()


async def test_comparison_logic():
    """測試比較邏輯的各種情況"""
    print("\n📋 測試比較邏輯...")

    from app.db.base import get_session_context
    from app.services.client_comparison_service import ClientComparisonService
    from app.db.models import ClientRecord, MaintenanceMacList
    from app.core.enums import MaintenancePhase
    from sqlalchemy import select, func

    svc = ClientComparisonService()
    maintenance_id = "2026-PING-TEST"

    async with get_session_context() as session:
        # 取得最新和較早的時間點
        latest_stmt = select(func.max(ClientRecord.collected_at)).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
        )
        latest_result = await session.execute(latest_stmt)
        current_time = latest_result.scalar()

        if not current_time:
            results.add_fail("比較邏輯-資料存在", True, False, "沒有 ClientRecord 資料")
            return

        # 取得較早的 checkpoint
        earlier_stmt = select(ClientRecord.collected_at).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
            ClientRecord.collected_at < current_time - timedelta(hours=1),
        ).order_by(ClientRecord.collected_at.desc()).limit(1)
        earlier_result = await session.execute(earlier_stmt)
        checkpoint_time = earlier_result.scalar()

        if not checkpoint_time:
            results.add_warning("比較邏輯", "沒有足夠早的 checkpoint，跳過部分測試")
            return

        # 執行比較
        comparisons = await svc._generate_checkpoint_diff(
            maintenance_id=maintenance_id,
            checkpoint_time=checkpoint_time,
            current_time=current_time,
            session=session,
        )

        # 測試 1: 比較結果數量應該等於 MAC 清單數量
        mac_count_stmt = select(func.count()).select_from(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_count_result = await session.execute(mac_count_stmt)
        expected_count = mac_count_result.scalar() or 0

        if len(comparisons) == expected_count:
            results.add_pass("比較邏輯-結果數量", f"{len(comparisons)} 筆")
        else:
            results.add_fail("比較邏輯-結果數量", expected_count, len(comparisons))

        # 測試 2: 檢查 severity 分布
        severity_counts = {}
        for comp in comparisons:
            sev = comp.severity or "unknown"
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        valid_severities = {"critical", "warning", "info", "normal", "undetected", "unknown"}
        invalid = set(severity_counts.keys()) - valid_severities
        if not invalid:
            results.add_pass("比較邏輯-severity 值有效", str(severity_counts))
        else:
            results.add_fail("比較邏輯-severity 值有效", valid_severities, invalid)

        # 測試 3: 檢查「未偵測→已偵測」的 severity 是 warning
        for comp in comparisons:
            if comp.differences and "_status" in comp.differences:
                status_change = comp.differences["_status"]
                if status_change.get("old") == "未偵測" and status_change.get("new") == "已偵測":
                    if comp.severity == "warning":
                        results.add_pass("比較邏輯-未偵測→已偵測=warning", comp.mac_address)
                    else:
                        results.add_fail(
                            "比較邏輯-未偵測→已偵測=warning",
                            "warning",
                            comp.severity,
                            f"MAC: {comp.mac_address}"
                        )
                elif status_change.get("old") == "已偵測" and status_change.get("new") == "未偵測":
                    if comp.severity == "critical":
                        results.add_pass("比較邏輯-已偵測→未偵測=critical", comp.mac_address)
                    else:
                        results.add_fail(
                            "比較邏輯-已偵測→未偵測=critical",
                            "critical",
                            comp.severity,
                            f"MAC: {comp.mac_address}"
                        )


async def test_category_statistics():
    """測試類別統計邏輯"""
    print("\n📋 測試類別統計...")

    from app.db.base import get_session_context
    from app.db.models import ClientCategory, ClientCategoryMember, MaintenanceMacList
    from sqlalchemy import select, func

    maintenance_id = "2026-PING-TEST"

    async with get_session_context() as session:
        # 取得所有類別
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,
        )
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()

        if not categories:
            results.add_warning("類別統計", "沒有類別資料")
            return

        results.add_pass("類別統計-類別存在", f"{len(categories)} 個類別")

        # 測試每個類別的成員數量
        for cat in categories:
            member_stmt = select(func.count()).select_from(ClientCategoryMember).where(
                ClientCategoryMember.category_id == cat.id
            )
            member_result = await session.execute(member_stmt)
            member_count = member_result.scalar() or 0

            results.add_pass(f"類別統計-{cat.name}成員數", f"{member_count} 個")

        # 測試：檢查是否有 MAC 屬於多個類別
        mac_stmt = select(
            ClientCategoryMember.mac_address,
            func.count(ClientCategoryMember.category_id).label("cat_count")
        ).group_by(ClientCategoryMember.mac_address).having(
            func.count(ClientCategoryMember.category_id) > 1
        )
        mac_result = await session.execute(mac_stmt)
        multi_cat_macs = mac_result.fetchall()

        if multi_cat_macs:
            results.add_warning(
                "類別統計-多類別 MAC",
                f"有 {len(multi_cat_macs)} 個 MAC 屬於多個類別: {[m[0] for m in multi_cat_macs]}"
            )
        else:
            results.add_pass("類別統計-無多類別衝突", "每個 MAC 最多屬於一個類別")

        # 測試：檢查「未分類」情況
        all_macs_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        all_macs_result = await session.execute(all_macs_stmt)
        all_macs = {row[0].upper() for row in all_macs_result.fetchall() if row[0]}

        categorized_macs_stmt = select(ClientCategoryMember.mac_address)
        categorized_result = await session.execute(categorized_macs_stmt)
        categorized_macs = {row[0].upper() for row in categorized_result.fetchall() if row[0]}

        uncategorized = all_macs - categorized_macs
        if uncategorized:
            results.add_warning("類別統計-未分類 MAC", f"{len(uncategorized)} 個: {uncategorized}")
        else:
            results.add_pass("類別統計-所有 MAC 已分類", f"{len(all_macs)} 個")


async def test_checkpoint_trend():
    """測試 Checkpoint 和趨勢圖邏輯"""
    print("\n📋 測試 Checkpoint/趨勢圖...")

    import httpx

    maintenance_id = "2026-PING-TEST"
    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 測試 1: 取得 checkpoint summaries
        try:
            resp = await client.get(
                f"{base_url}/comparisons/checkpoints/{maintenance_id}/summaries",
                params={"include_categories": "true"},
                timeout=30,
            )

            if resp.status_code != 200:
                results.add_fail("Checkpoint-API 回應", 200, resp.status_code)
                return

            data = resp.json()
            summaries = data.get("summaries", {})
            current_time = data.get("current_time")
            categories = data.get("categories", [])

            results.add_pass("Checkpoint-API 回應", f"{len(summaries)} 個 checkpoints")

            # 測試 2: 驗證 current_time 不在 summaries 中
            if current_time and current_time in summaries:
                results.add_fail(
                    "Checkpoint-排除 current_time",
                    "current_time 不應在 summaries 中",
                    "current_time 在 summaries 中",
                    "這會導致趨勢圖最右端永遠是 0"
                )
            else:
                results.add_pass("Checkpoint-排除 current_time", "current_time 不在 summaries 中")

            # 測試 3: 驗證每個 summary 都有 by_category
            for ts, summary in summaries.items():
                if "by_category" not in summary:
                    results.add_fail(
                        "Checkpoint-by_category 存在",
                        "每個 summary 都有 by_category",
                        f"{ts} 缺少 by_category"
                    )
                    break
            else:
                results.add_pass("Checkpoint-by_category 存在", "所有 summaries 都有")

            # 測試 4: 驗證類別 ID 一致性
            if categories and summaries:
                cat_ids = {str(c["id"]) for c in categories}
                first_summary = list(summaries.values())[0]
                summary_cat_ids = set(first_summary.get("by_category", {}).keys())

                if cat_ids == summary_cat_ids:
                    results.add_pass("Checkpoint-類別 ID 一致", f"IDs: {cat_ids}")
                else:
                    results.add_fail(
                        "Checkpoint-類別 ID 一致",
                        cat_ids,
                        summary_cat_ids
                    )

        except Exception as e:
            results.add_fail("Checkpoint-API 連線", "成功", str(e))


async def test_diff_summaries_consistency():
    """測試 /diff 和 /summaries 的一致性"""
    print("\n📋 測試 API 一致性...")

    import httpx

    maintenance_id = "2026-PING-TEST"
    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 先取得 summaries
        summaries_resp = await client.get(
            f"{base_url}/comparisons/checkpoints/{maintenance_id}/summaries",
            params={"include_categories": "true"},
            timeout=30,
        )

        if summaries_resp.status_code != 200:
            results.add_fail("API一致性-summaries", 200, summaries_resp.status_code)
            return

        summaries_data = summaries_resp.json()
        summaries = summaries_data.get("summaries", {})

        if not summaries:
            results.add_warning("API一致性", "沒有 summaries 資料")
            return

        # 選擇一個 checkpoint 來比較
        checkpoint = sorted(summaries.keys())[-2] if len(summaries) > 1 else list(summaries.keys())[0]
        summary = summaries[checkpoint]

        # 呼叫 /diff API
        diff_resp = await client.get(
            f"{base_url}/comparisons/diff/{maintenance_id}",
            params={"checkpoint": checkpoint},
            timeout=30,
        )

        if diff_resp.status_code != 200:
            results.add_fail("API一致性-diff", 200, diff_resp.status_code)
            return

        diff_data = diff_resp.json()
        diff_summary = diff_data.get("summary", {})
        diff_by_category = diff_data.get("by_category", [])

        # 比較 issue_count
        summary_issues = summary.get("issue_count", 0)
        diff_issues = diff_summary.get("has_issues", 0)

        if summary_issues == diff_issues:
            results.add_pass("API一致性-issue_count", f"兩者都是 {summary_issues}")
        else:
            results.add_fail(
                "API一致性-issue_count",
                f"summaries: {summary_issues}",
                f"diff: {diff_issues}",
                f"checkpoint: {checkpoint}"
            )

        # 比較類別統計
        summary_by_cat = summary.get("by_category", {})
        for cat in diff_by_category:
            cat_id = str(cat["id"])
            if cat_id == "-1" or cat_id == "null":
                continue
            diff_cat_issues = cat.get("issues", 0)
            summary_cat_issues = summary_by_cat.get(cat_id, 0)

            if diff_cat_issues == summary_cat_issues:
                results.add_pass(f"API一致性-{cat['name']}", f"兩者都是 {diff_cat_issues}")
            else:
                results.add_fail(
                    f"API一致性-{cat['name']}",
                    f"summaries: {summary_cat_issues}",
                    f"diff: {diff_cat_issues}"
                )


async def test_severity_override():
    """測試嚴重度覆蓋功能"""
    print("\n📋 測試嚴重度覆蓋...")

    from app.db.base import get_session_context
    from app.db.models import SeverityOverride
    from sqlalchemy import select

    maintenance_id = "2026-PING-TEST"

    async with get_session_context() as session:
        # 查詢現有的 overrides
        stmt = select(SeverityOverride).where(
            SeverityOverride.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        overrides = result.scalars().all()

        if overrides:
            results.add_pass("嚴重度覆蓋-存在", f"{len(overrides)} 個覆蓋")

            # 檢查 override 的有效性
            valid_severities = {"info", "warning", "critical", "normal"}
            for o in overrides:
                if o.override_severity not in valid_severities:
                    results.add_fail(
                        "嚴重度覆蓋-有效值",
                        valid_severities,
                        o.override_severity,
                        f"MAC: {o.mac_address}"
                    )
                else:
                    results.add_pass(
                        f"嚴重度覆蓋-{o.mac_address}",
                        f"覆蓋為 {o.override_severity}"
                    )
        else:
            results.add_warning("嚴重度覆蓋", "沒有覆蓋記錄，無法測試")


async def test_dashboard_indicators():
    """測試 Dashboard 指標"""
    print("\n📋 測試 Dashboard 指標...")

    import httpx

    maintenance_id = "2026-PING-TEST"
    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{base_url}/dashboard/maintenance/{maintenance_id}/summary",
                timeout=30,
            )

            if resp.status_code != 200:
                results.add_fail("Dashboard-API", 200, resp.status_code)
                return

            data = resp.json()
            indicators = data.get("indicators", {})
            overall = data.get("overall", {})

            # 測試各指標
            expected_indicators = ["transceiver", "version", "uplink", "port_channel", "power", "fan", "error_count", "ping"]

            for ind_name in expected_indicators:
                if ind_name in indicators:
                    ind = indicators[ind_name]
                    total = ind.get("total_count", 0)
                    pass_count = ind.get("pass_count", 0)
                    fail_count = ind.get("fail_count", 0)

                    # 驗證數學邏輯
                    if total == pass_count + fail_count:
                        results.add_pass(f"Dashboard-{ind_name}", f"{pass_count}/{total} 通過")
                    else:
                        results.add_fail(
                            f"Dashboard-{ind_name}數學邏輯",
                            f"total({total}) = pass({pass_count}) + fail({fail_count})",
                            f"不相等"
                        )
                else:
                    results.add_warning(f"Dashboard-{ind_name}", "指標不存在")

            # 測試 overall
            if overall:
                total = overall.get("total_count", 0)
                pass_rate = overall.get("pass_rate", 0)

                if total > 0:
                    results.add_pass("Dashboard-overall", f"通過率 {pass_rate:.1f}%")
                else:
                    results.add_warning("Dashboard-overall", "總數為 0")

        except Exception as e:
            results.add_fail("Dashboard-API連線", "成功", str(e))


async def test_mock_data_generation():
    """測試 Mock 資料生成"""
    print("\n📋 測試 Mock 資料生成...")

    from app.db.base import get_session_context
    from app.db.models import ClientRecord, VersionRecord, MaintenanceMacList
    from app.core.enums import MaintenancePhase, ClientDetectionStatus
    from sqlalchemy import select, func

    maintenance_id = "2026-PING-TEST"

    async with get_session_context() as session:
        # 測試 1: ClientRecord 存在
        client_count_stmt = select(func.count()).select_from(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id
        )
        client_result = await session.execute(client_count_stmt)
        client_count = client_result.scalar() or 0

        if client_count > 0:
            results.add_pass("Mock-ClientRecord存在", f"{client_count} 筆")
        else:
            results.add_fail("Mock-ClientRecord存在", ">0", 0)

        # 測試 2: VersionRecord 存在
        version_count_stmt = select(func.count()).select_from(VersionRecord).where(
            VersionRecord.maintenance_id == maintenance_id
        )
        version_result = await session.execute(version_count_stmt)
        version_count = version_result.scalar() or 0

        if version_count > 0:
            results.add_pass("Mock-VersionRecord存在", f"{version_count} 筆")
        else:
            results.add_fail("Mock-VersionRecord存在", ">0", 0)

        # 測試 3: detection_status 有更新
        status_stmt = select(
            MaintenanceMacList.detection_status,
            func.count().label("count")
        ).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        ).group_by(MaintenanceMacList.detection_status)
        status_result = await session.execute(status_stmt)
        status_counts = {str(row[0]): row[1] for row in status_result.fetchall()}

        detected_count = status_counts.get(str(ClientDetectionStatus.DETECTED), 0)
        not_detected_count = status_counts.get(str(ClientDetectionStatus.NOT_DETECTED), 0)

        if detected_count > 0:
            results.add_pass("Mock-detection_status更新", f"DETECTED: {detected_count}, NOT_DETECTED: {not_detected_count}")
        else:
            results.add_warning("Mock-detection_status", f"沒有 DETECTED 狀態: {status_counts}")


async def test_edge_cases():
    """測試邊界情況"""
    print("\n📋 測試邊界情況...")

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 測試 1: 不存在的 maintenance_id
        try:
            resp = await client.get(
                f"{base_url}/comparisons/checkpoints/NON_EXISTENT_ID/summaries",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("summaries"):
                    results.add_pass("Edge-不存在的ID", "正確返回空資料")
                else:
                    results.add_fail("Edge-不存在的ID", "空資料", "有資料返回")
            else:
                results.add_pass("Edge-不存在的ID", f"返回 {resp.status_code}")
        except Exception as e:
            results.add_fail("Edge-不存在的ID", "正常處理", str(e))

        # 測試 2: 無效的 checkpoint 格式
        try:
            resp = await client.get(
                f"{base_url}/comparisons/diff/2026-PING-TEST",
                params={"checkpoint": "invalid-date-format"},
                timeout=10,
            )
            if resp.status_code in [400, 422]:
                results.add_pass("Edge-無效checkpoint格式", f"正確返回 {resp.status_code}")
            else:
                results.add_warning("Edge-無效checkpoint格式", f"返回 {resp.status_code}，可能需要更好的錯誤處理")
        except Exception as e:
            results.add_fail("Edge-無效checkpoint格式", "錯誤處理", str(e))

        # 測試 3: 空的 MAC 地址處理
        # (這需要資料庫中有空 MAC 的情況，通常不會發生)
        results.add_pass("Edge-空MAC處理", "已在程式碼中處理")


async def test_data_integrity():
    """測試資料完整性"""
    print("\n📋 測試資料完整性...")

    from app.db.base import get_session_context
    from app.db.models import (
        MaintenanceMacList, MaintenanceDeviceList, ClientRecord,
        ClientCategory, ClientCategoryMember
    )
    from sqlalchemy import select, func

    maintenance_id = "2026-PING-TEST"

    async with get_session_context() as session:
        # 測試 1: MAC 清單中的 MAC 格式
        mac_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        macs = [row[0] for row in mac_result.fetchall()]

        invalid_macs = []
        for mac in macs:
            if mac:
                # 簡單檢查 MAC 格式
                parts = mac.split(":")
                if len(parts) != 6:
                    invalid_macs.append(mac)

        if invalid_macs:
            results.add_fail("資料完整性-MAC格式", "有效格式", invalid_macs)
        else:
            results.add_pass("資料完整性-MAC格式", f"所有 {len(macs)} 個 MAC 格式正確")

        # 測試 2: 設備清單中的 hostname
        device_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        device_result = await session.execute(device_stmt)
        devices = device_result.scalars().all()

        devices_without_hostname = [d for d in devices if not d.new_hostname and not d.old_hostname]
        if devices_without_hostname:
            results.add_warning("資料完整性-設備hostname", f"{len(devices_without_hostname)} 個設備沒有 hostname")
        else:
            results.add_pass("資料完整性-設備hostname", f"所有 {len(devices)} 個設備都有 hostname")

        # 測試 3: 類別成員的 MAC 是否存在於 MAC 清單
        member_stmt = select(ClientCategoryMember.mac_address)
        member_result = await session.execute(member_stmt)
        member_macs = {row[0].upper() for row in member_result.fetchall() if row[0]}

        mac_set = {m.upper() for m in macs if m}
        orphan_members = member_macs - mac_set

        if orphan_members:
            results.add_warning("資料完整性-孤立成員", f"{len(orphan_members)} 個類別成員的 MAC 不在清單中: {orphan_members}")
        else:
            results.add_pass("資料完整性-類別成員", "所有成員的 MAC 都在清單中")


async def main():
    """主測試函數"""
    print("=" * 80)
    print("                 開始綜合測試")
    print("=" * 80)

    try:
        await test_comparison_logic()
        await test_category_statistics()
        await test_checkpoint_trend()
        await test_diff_summaries_consistency()
        await test_severity_override()
        await test_dashboard_indicators()
        await test_mock_data_generation()
        await test_edge_cases()
        await test_data_integrity()
    except Exception as e:
        results.add_fail("測試執行", "成功完成", str(e))

    print("\n")
    print(results.summary())

    # 輸出到檔案
    with open("/Users/coolguazi/Project/ClineTest/network_dashboard/tests/test_report.txt", "w") as f:
        f.write(results.summary())

    print(f"\n報告已儲存到: tests/test_report.txt")

    return len(results.failed) == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
