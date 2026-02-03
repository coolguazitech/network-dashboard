"""
Comprehensive System Testing Script V2

更嚴格、更全面的測試，包含：
1. 多歲修資料測試
2. 每項功能多個邊界情況
3. 邏輯交互影響測試
4. 資料一致性深度檢查
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from typing import Any
from collections import defaultdict

sys.path.insert(0, "/Users/coolguazi/Project/ClineTest/network_dashboard")


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.categories = defaultdict(lambda: {"passed": 0, "failed": 0, "warnings": 0})

    def add_pass(self, category: str, test_name: str, details: str = ""):
        self.passed.append({"category": category, "name": test_name, "details": details})
        self.categories[category]["passed"] += 1

    def add_fail(self, category: str, test_name: str, expected: Any, actual: Any, details: str = ""):
        self.failed.append({
            "category": category,
            "name": test_name,
            "expected": expected,
            "actual": actual,
            "details": details,
        })
        self.categories[category]["failed"] += 1

    def add_warning(self, category: str, test_name: str, message: str):
        self.warnings.append({"category": category, "name": test_name, "message": message})
        self.categories[category]["warnings"] += 1

    def summary(self) -> str:
        lines = []
        lines.append("=" * 100)
        lines.append("                         綜合測試報告 V2 (Comprehensive Test Report)")
        lines.append("=" * 100)
        lines.append(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(f"{'總計':=^96}")
        lines.append(f"✅ 通過: {len(self.passed)}  |  ❌ 失敗: {len(self.failed)}  |  ⚠️ 警告: {len(self.warnings)}")
        lines.append("")

        # 按類別統計
        lines.append(f"{'按類別統計':=^96}")
        for cat, stats in sorted(self.categories.items()):
            status = "✅" if stats["failed"] == 0 else "❌"
            lines.append(f"{status} {cat}: 通過 {stats['passed']} | 失敗 {stats['failed']} | 警告 {stats['warnings']}")

        if self.failed:
            lines.append("")
            lines.append(f"{'失敗的測試':=^96}")
            for i, f in enumerate(self.failed, 1):
                lines.append(f"\n{i}. [{f['category']}] {f['name']}")
                lines.append(f"   期望: {f['expected']}")
                lines.append(f"   實際: {f['actual']}")
                if f['details']:
                    lines.append(f"   詳情: {f['details']}")

        if self.warnings:
            lines.append("")
            lines.append(f"{'警告':=^96}")
            for w in self.warnings:
                lines.append(f"  ⚠️ [{w['category']}] {w['name']}: {w['message']}")

        lines.append("")
        lines.append("=" * 100)
        return "\n".join(lines)


results = TestResult()


# =============================================================================
# 1. 多歲修資料測試
# =============================================================================
async def test_multiple_maintenances():
    """測試多個歲修的資料隔離和正確性"""
    print("\n📋 [1] 測試多歲修資料隔離...")
    cat = "多歲修隔離"

    from app.db.base import get_session_context
    from app.db.models import MaintenanceConfig, MaintenanceMacList, ClientRecord
    from sqlalchemy import select, func

    async with get_session_context() as session:
        # 取得所有歲修
        stmt = select(MaintenanceConfig)
        result = await session.execute(stmt)
        maintenances = result.scalars().all()

        if len(maintenances) == 0:
            results.add_fail(cat, "歲修存在", "至少 1 個", 0)
            return

        results.add_pass(cat, "歲修數量", f"{len(maintenances)} 個歲修")

        # 測試每個歲修的資料隔離
        for maint in maintenances:
            mid = maint.maintenance_id

            # MAC 清單數量
            mac_stmt = select(func.count()).select_from(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == mid
            )
            mac_result = await session.execute(mac_stmt)
            mac_count = mac_result.scalar() or 0

            # ClientRecord 數量
            record_stmt = select(func.count()).select_from(ClientRecord).where(
                ClientRecord.maintenance_id == mid
            )
            record_result = await session.execute(record_stmt)
            record_count = record_result.scalar() or 0

            results.add_pass(cat, f"{mid}-MAC數量", f"{mac_count} 個")
            results.add_pass(cat, f"{mid}-ClientRecord數量", f"{record_count} 筆")

            # 驗證 ClientRecord 的 MAC 都在 MAC 清單中
            if mac_count > 0 and record_count > 0:
                mac_list_stmt = select(MaintenanceMacList.mac_address).where(
                    MaintenanceMacList.maintenance_id == mid
                )
                mac_list_result = await session.execute(mac_list_stmt)
                valid_macs = {row[0].upper() for row in mac_list_result.fetchall() if row[0]}

                record_mac_stmt = select(ClientRecord.mac_address).where(
                    ClientRecord.maintenance_id == mid
                ).distinct()
                record_mac_result = await session.execute(record_mac_stmt)
                # 排除系統標記 MAC（如 __MARKER__，用於記錄快照時間點）
                record_macs = {
                    row[0].upper() for row in record_mac_result.fetchall()
                    if row[0] and not row[0].startswith("__")
                }

                invalid_macs = record_macs - valid_macs
                if invalid_macs:
                    results.add_fail(
                        cat,
                        f"{mid}-MAC一致性",
                        "所有 ClientRecord MAC 在清單中",
                        f"有 {len(invalid_macs)} 個不在清單中: {list(invalid_macs)[:3]}..."
                    )
                else:
                    results.add_pass(cat, f"{mid}-MAC一致性", "所有 MAC 都在清單中")


# =============================================================================
# 2. 比較邏輯深度測試
# =============================================================================
async def test_comparison_logic_deep():
    """深度測試比較邏輯的各種情況"""
    print("\n📋 [2] 深度測試比較邏輯...")
    cat = "比較邏輯"

    from app.db.base import get_session_context
    from app.services.client_comparison_service import ClientComparisonService
    from app.db.models import ClientRecord, MaintenanceMacList
    from app.core.enums import MaintenancePhase
    from sqlalchemy import select, func

    svc = ClientComparisonService()

    async with get_session_context() as session:
        # 取得所有有資料的歲修
        maint_stmt = select(ClientRecord.maintenance_id).distinct()
        maint_result = await session.execute(maint_stmt)
        maintenance_ids = [row[0] for row in maint_result.fetchall()]

        if not maintenance_ids:
            results.add_fail(cat, "有資料的歲修", "至少 1 個", 0)
            return

        for mid in maintenance_ids:
            # 取得最新時間
            latest_stmt = select(func.max(ClientRecord.collected_at)).where(
                ClientRecord.maintenance_id == mid,
                ClientRecord.phase == MaintenancePhase.NEW,
            )
            latest_result = await session.execute(latest_stmt)
            current_time = latest_result.scalar()

            if not current_time:
                continue

            # 取得多個不同時間點的 checkpoint
            checkpoints_stmt = select(ClientRecord.collected_at).where(
                ClientRecord.maintenance_id == mid,
                ClientRecord.phase == MaintenancePhase.NEW,
            ).distinct().order_by(ClientRecord.collected_at)
            checkpoints_result = await session.execute(checkpoints_stmt)
            all_checkpoints = [row[0] for row in checkpoints_result.fetchall()]

            # 篩選出與 current_time 不同的 checkpoint
            valid_checkpoints = [
                cp for cp in all_checkpoints
                if abs((cp - current_time).total_seconds()) > 60
            ]

            if len(valid_checkpoints) < 2:
                results.add_warning(cat, f"{mid}-checkpoint數量", f"只有 {len(valid_checkpoints)} 個有效 checkpoint")
                continue

            # 測試多個 checkpoint
            test_checkpoints = [
                valid_checkpoints[0],  # 最早的
                valid_checkpoints[len(valid_checkpoints)//2],  # 中間的
                valid_checkpoints[-1],  # 最新的
            ]

            severity_distribution = defaultdict(int)
            change_types = defaultdict(int)

            for checkpoint_time in test_checkpoints:
                comparisons = await svc._generate_checkpoint_diff(
                    maintenance_id=mid,
                    checkpoint_time=checkpoint_time,
                    current_time=current_time,
                    session=session,
                )

                for comp in comparisons:
                    severity_distribution[comp.severity or "unknown"] += 1

                    # 統計變化類型
                    if comp.differences:
                        for key in comp.differences.keys():
                            change_types[key] += 1

            # 驗證 severity 分布
            valid_severities = {"critical", "warning", "info", "normal", "undetected", "unknown"}
            invalid = set(severity_distribution.keys()) - valid_severities
            if invalid:
                results.add_fail(cat, f"{mid}-severity有效性", valid_severities, invalid)
            else:
                results.add_pass(cat, f"{mid}-severity分布", dict(severity_distribution))

            # 記錄變化類型統計
            if change_types:
                results.add_pass(cat, f"{mid}-變化類型", dict(change_types))


# =============================================================================
# 3. Severity 計算邏輯測試
# =============================================================================
async def test_severity_calculation():
    """測試 severity 計算的各種情況"""
    print("\n📋 [3] 測試 Severity 計算邏輯...")
    cat = "Severity計算"

    from app.services.client_comparison_service import ClientComparisonService
    from app.db.models import ClientComparison

    svc = ClientComparisonService()

    # 測試用例：(old_detected, new_detected, expected_severity, description)
    test_cases = [
        # 基本偵測狀態變化
        (False, False, "undetected", "兩邊都未偵測"),
        (True, False, "critical", "已偵測→未偵測"),
        (False, True, "warning", "未偵測→已偵測"),
    ]

    for old_det, new_det, expected_sev, desc in test_cases:
        comp = ClientComparison(
            mac_address="TEST:MAC:00:00:00:01",
            maintenance_id="TEST",
        )

        # 模擬有/無資料
        if old_det:
            comp.old_switch_hostname = "SW-OLD-001"
            comp.old_interface_name = "GE1/0/1"
        if new_det:
            comp.new_switch_hostname = "SW-NEW-001"
            comp.new_interface_name = "GE1/0/1"

        # 執行比較
        result = svc._compare_records(comp, {})

        if result.severity == expected_sev:
            results.add_pass(cat, f"偵測狀態-{desc}", f"severity={expected_sev}")
        else:
            results.add_fail(cat, f"偵測狀態-{desc}", expected_sev, result.severity)

    # 測試欄位變化的 severity
    field_test_cases = [
        # (field_name, old_value, new_value, expected_severity)
        ("link_status", "up", "down", "critical"),  # 惡化
        ("link_status", "down", "up", "warning"),   # 改善
        ("ping_reachable", True, False, "critical"),  # 惡化
        ("ping_reachable", False, True, "warning"),   # 改善
        ("speed", "1G", "10G", "warning"),  # 速度變化
        ("switch_hostname", "SW-A", "SW-B", "critical"),  # 交換機變化
    ]

    for field, old_val, new_val, expected_sev in field_test_cases:
        comp = ClientComparison(
            mac_address="TEST:MAC:00:00:00:02",
            maintenance_id="TEST",
        )

        # 設置基本資料
        comp.old_switch_hostname = "SW-OLD-001"
        comp.old_interface_name = "GE1/0/1"
        comp.new_switch_hostname = "SW-NEW-001"
        comp.new_interface_name = "GE1/0/1"

        # 設置測試欄位
        setattr(comp, f"old_{field}", old_val)
        setattr(comp, f"new_{field}", new_val)

        result = svc._compare_records(comp, {})

        # 只檢查是否有變化被偵測到
        if result.is_changed:
            results.add_pass(cat, f"欄位變化-{field}", f"{old_val}→{new_val} 偵測到變化")
        else:
            results.add_warning(cat, f"欄位變化-{field}", f"{old_val}→{new_val} 未偵測到變化")


# =============================================================================
# 4. Severity Override 完整測試
# =============================================================================
async def test_severity_override_complete():
    """完整測試 severity override 功能"""
    print("\n📋 [4] 完整測試 Severity Override...")
    cat = "Override功能"

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 取得所有歲修
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig
        from sqlalchemy import select

        async with get_session_context() as session:
            stmt = select(MaintenanceConfig.maintenance_id)
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        for mid in maintenance_ids:
            # 測試取得 override 列表
            try:
                resp = await client.get(
                    f"{base_url}/comparisons/overrides/{mid}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    overrides = data.get("overrides", [])
                    results.add_pass(cat, f"{mid}-取得Override", f"{len(overrides)} 個")

                    # 驗證每個 override 的結構
                    for o in overrides:
                        required_fields = ["mac_address", "override_severity"]
                        missing = [f for f in required_fields if f not in o]
                        if missing:
                            results.add_fail(cat, f"{mid}-Override結構", required_fields, f"缺少: {missing}")
                        else:
                            # 驗證 severity 值
                            valid_values = {"info", "warning", "critical", "normal"}
                            if o["override_severity"] not in valid_values:
                                results.add_fail(
                                    cat,
                                    f"{mid}-Override值有效",
                                    valid_values,
                                    o["override_severity"]
                                )
                else:
                    results.add_warning(cat, f"{mid}-取得Override", f"HTTP {resp.status_code}")
            except Exception as e:
                results.add_fail(cat, f"{mid}-取得Override", "成功", str(e))


# =============================================================================
# 5. 類別統計交叉驗證
# =============================================================================
async def test_category_cross_validation():
    """交叉驗證類別統計的正確性"""
    print("\n📋 [5] 類別統計交叉驗證...")
    cat = "類別統計"

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig
        from sqlalchemy import select

        async with get_session_context() as session:
            stmt = select(MaintenanceConfig.maintenance_id)
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        for mid in maintenance_ids:
            # 取得 summaries
            summaries_resp = await client.get(
                f"{base_url}/comparisons/checkpoints/{mid}/summaries",
                params={"include_categories": "true"},
                timeout=30,
            )

            if summaries_resp.status_code != 200:
                results.add_warning(cat, f"{mid}-summaries", f"HTTP {summaries_resp.status_code}")
                continue

            summaries_data = summaries_resp.json()
            summaries = summaries_data.get("summaries", {})
            categories = summaries_data.get("categories", [])

            if not summaries:
                results.add_warning(cat, f"{mid}-summaries", "無資料")
                continue

            # 對每個 checkpoint 驗證
            for checkpoint, summary in list(summaries.items())[:3]:  # 只測前 3 個
                # 取得對應的 diff
                diff_resp = await client.get(
                    f"{base_url}/comparisons/diff/{mid}",
                    params={"checkpoint": checkpoint},
                    timeout=30,
                )

                if diff_resp.status_code != 200:
                    results.add_warning(cat, f"{mid}-diff-{checkpoint[:10]}", f"HTTP {diff_resp.status_code}")
                    continue

                diff_data = diff_resp.json()
                diff_by_cat = {str(c["id"]): c for c in diff_data.get("by_category", [])}

                # 比較每個類別的 issue 數量
                summary_by_cat = summary.get("by_category", {})

                for cat_info in categories:
                    cat_id = str(cat_info["id"])
                    cat_name = cat_info["name"]

                    summary_issues = summary_by_cat.get(cat_id, 0)
                    diff_issues = diff_by_cat.get(cat_id, {}).get("issues", 0)

                    if summary_issues == diff_issues:
                        results.add_pass(
                            cat,
                            f"{mid}-{cat_name}-一致性",
                            f"checkpoint {checkpoint[:10]}: {summary_issues}"
                        )
                    else:
                        results.add_fail(
                            cat,
                            f"{mid}-{cat_name}-一致性",
                            f"summaries: {summary_issues}",
                            f"diff: {diff_issues}",
                            f"checkpoint: {checkpoint}"
                        )


# =============================================================================
# 6. 趨勢圖資料完整性測試
# =============================================================================
async def test_trend_data_integrity():
    """測試趨勢圖資料的完整性和連續性"""
    print("\n📋 [6] 測試趨勢圖資料完整性...")
    cat = "趨勢圖"

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig
        from sqlalchemy import select

        async with get_session_context() as session:
            stmt = select(MaintenanceConfig.maintenance_id)
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        for mid in maintenance_ids:
            resp = await client.get(
                f"{base_url}/comparisons/checkpoints/{mid}/summaries",
                params={"include_categories": "true"},
                timeout=30,
            )

            if resp.status_code != 200:
                continue

            data = resp.json()
            summaries = data.get("summaries", {})
            current_time = data.get("current_time")
            categories = data.get("categories", [])

            if not summaries:
                continue

            # 測試 1: current_time 不在 summaries 中
            if current_time in summaries:
                results.add_fail(
                    cat,
                    f"{mid}-current排除",
                    "current_time 不在 summaries",
                    "current_time 在 summaries 中"
                )
            else:
                results.add_pass(cat, f"{mid}-current排除", "current_time 已排除")

            # 測試 2: 時間順序正確
            sorted_times = sorted(summaries.keys())
            if sorted_times == list(summaries.keys()) or sorted_times == list(reversed(summaries.keys())):
                results.add_pass(cat, f"{mid}-時間順序", f"{len(sorted_times)} 個時間點")
            else:
                results.add_warning(cat, f"{mid}-時間順序", "時間順序不一致")

            # 測試 3: 每個 summary 都有完整的類別資料
            for ts, summary in summaries.items():
                by_cat = summary.get("by_category", {})
                expected_cat_ids = {str(c["id"]) for c in categories}
                actual_cat_ids = set(by_cat.keys())

                if expected_cat_ids != actual_cat_ids:
                    results.add_fail(
                        cat,
                        f"{mid}-類別完整性-{ts[:10]}",
                        expected_cat_ids,
                        actual_cat_ids
                    )
                    break
            else:
                results.add_pass(cat, f"{mid}-類別完整性", "所有 checkpoint 都有完整類別")

            # 測試 4: issue_count 不為負數
            for ts, summary in summaries.items():
                if summary.get("issue_count", 0) < 0:
                    results.add_fail(cat, f"{mid}-issue非負", ">=0", summary["issue_count"])
                    break
                for cat_id, count in summary.get("by_category", {}).items():
                    if count < 0:
                        results.add_fail(cat, f"{mid}-類別issue非負", ">=0", count)
                        break
            else:
                results.add_pass(cat, f"{mid}-issue非負", "所有值都 >= 0")


# =============================================================================
# 7. Dashboard 指標數學邏輯測試
# =============================================================================
async def test_dashboard_math_logic():
    """測試 Dashboard 指標的數學邏輯"""
    print("\n📋 [7] 測試 Dashboard 數學邏輯...")
    cat = "Dashboard數學"

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig
        from sqlalchemy import select

        async with get_session_context() as session:
            stmt = select(MaintenanceConfig.maintenance_id)
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        for mid in maintenance_ids:
            resp = await client.get(
                f"{base_url}/dashboard/maintenance/{mid}/summary",
                timeout=30,
            )

            if resp.status_code != 200:
                continue

            data = resp.json()
            indicators = data.get("indicators", {})
            overall = data.get("overall", {})

            # 測試每個指標的數學邏輯
            for ind_name, ind in indicators.items():
                total = ind.get("total_count", 0)
                pass_count = ind.get("pass_count", 0)
                fail_count = ind.get("fail_count", 0)
                pass_rate = ind.get("pass_rate", 0)

                # 驗證 total = pass + fail
                if total != pass_count + fail_count:
                    results.add_fail(
                        cat,
                        f"{mid}-{ind_name}-加總",
                        f"total({total}) = pass({pass_count}) + fail({fail_count})",
                        "不相等"
                    )
                else:
                    results.add_pass(cat, f"{mid}-{ind_name}-加總", f"{pass_count}+{fail_count}={total}")

                # 驗證 pass_rate 計算
                if total > 0:
                    expected_rate = (pass_count / total) * 100
                    if abs(pass_rate - expected_rate) > 0.01:
                        results.add_fail(
                            cat,
                            f"{mid}-{ind_name}-通過率",
                            f"{expected_rate:.2f}%",
                            f"{pass_rate:.2f}%"
                        )
                    else:
                        results.add_pass(cat, f"{mid}-{ind_name}-通過率", f"{pass_rate:.1f}%")

            # 驗證 overall
            if overall:
                total_overall = sum(ind.get("total_count", 0) for ind in indicators.values())
                pass_overall = sum(ind.get("pass_count", 0) for ind in indicators.values())

                if overall.get("total_count") == total_overall:
                    results.add_pass(cat, f"{mid}-overall-total", f"{total_overall}")
                else:
                    results.add_fail(
                        cat,
                        f"{mid}-overall-total",
                        total_overall,
                        overall.get("total_count")
                    )


# =============================================================================
# 8. 邊界情況和錯誤處理測試
# =============================================================================
async def test_edge_cases_complete():
    """完整的邊界情況測試"""
    print("\n📋 [8] 邊界情況測試...")
    cat = "邊界情況"

    import httpx

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 測試 1: 不存在的 maintenance_id
        test_ids = [
            "NON_EXISTENT_ID",
            "",
            "a" * 1000,  # 超長 ID
            "test'injection",  # SQL injection attempt
            "test<script>",  # XSS attempt
        ]

        for test_id in test_ids:
            try:
                resp = await client.get(
                    f"{base_url}/comparisons/checkpoints/{test_id}/summaries",
                    timeout=10,
                )
                if resp.status_code in [200, 404]:
                    results.add_pass(cat, f"無效ID-{test_id[:20]}", f"HTTP {resp.status_code}")
                elif resp.status_code >= 500:
                    results.add_fail(cat, f"無效ID-{test_id[:20]}", "不應該 5xx", resp.status_code)
                else:
                    results.add_pass(cat, f"無效ID-{test_id[:20]}", f"HTTP {resp.status_code}")
            except Exception as e:
                results.add_fail(cat, f"無效ID-{test_id[:20]}", "正常處理", str(e)[:50])

        # 測試 2: 無效的 checkpoint 格式
        invalid_checkpoints = [
            "invalid",
            "2024-13-45",  # 無效日期
            "not-a-date",
            "",
            "2024-01-01T25:00:00",  # 無效時間
        ]

        for cp in invalid_checkpoints:
            try:
                resp = await client.get(
                    f"{base_url}/comparisons/diff/2026-PING-TEST",
                    params={"checkpoint": cp},
                    timeout=10,
                )
                if resp.status_code == 400:
                    results.add_pass(cat, f"無效checkpoint-{cp[:15]}", "正確返回 400")
                elif resp.status_code >= 500:
                    results.add_fail(cat, f"無效checkpoint-{cp[:15]}", "400", resp.status_code)
                else:
                    results.add_warning(cat, f"無效checkpoint-{cp[:15]}", f"HTTP {resp.status_code}")
            except Exception as e:
                results.add_fail(cat, f"無效checkpoint-{cp[:15]}", "正常處理", str(e)[:50])

        # 測試 3: 超出範圍的參數
        try:
            resp = await client.get(
                f"{base_url}/comparisons/checkpoints/2026-PING-TEST/summaries",
                params={"max_days": 999},
                timeout=10,
            )
            if resp.status_code in [200, 400, 422]:
                results.add_pass(cat, "超大max_days", f"HTTP {resp.status_code}")
            else:
                results.add_warning(cat, "超大max_days", f"HTTP {resp.status_code}")
        except Exception as e:
            results.add_fail(cat, "超大max_days", "正常處理", str(e)[:50])


# =============================================================================
# 9. 資料一致性深度檢查
# =============================================================================
async def test_data_consistency_deep():
    """深度檢查資料一致性"""
    print("\n📋 [9] 資料一致性深度檢查...")
    cat = "資料一致性"

    from app.db.base import get_session_context
    from app.db.models import (
        MaintenanceConfig, MaintenanceMacList, MaintenanceDeviceList,
        ClientRecord, ClientCategory, ClientCategoryMember,
        VersionRecord, VersionExpectation
    )
    from sqlalchemy import select, func

    async with get_session_context() as session:
        # 取得所有歲修
        stmt = select(MaintenanceConfig)
        result = await session.execute(stmt)
        maintenances = result.scalars().all()

        for maint in maintenances:
            mid = maint.maintenance_id

            # 測試 1: 類別成員的 MAC 必須在 MAC 清單中
            mac_list_stmt = select(MaintenanceMacList.mac_address).where(
                MaintenanceMacList.maintenance_id == mid
            )
            mac_list_result = await session.execute(mac_list_stmt)
            valid_macs = {row[0].upper() for row in mac_list_result.fetchall() if row[0]}

            cat_stmt = select(ClientCategory.id).where(
                ClientCategory.maintenance_id == mid
            )
            cat_result = await session.execute(cat_stmt)
            cat_ids = [row[0] for row in cat_result.fetchall()]

            if cat_ids:
                member_stmt = select(ClientCategoryMember.mac_address).where(
                    ClientCategoryMember.category_id.in_(cat_ids)
                )
                member_result = await session.execute(member_stmt)
                member_macs = {row[0].upper() for row in member_result.fetchall() if row[0]}

                orphan = member_macs - valid_macs
                if orphan:
                    results.add_warning(cat, f"{mid}-孤立成員", f"{len(orphan)} 個 MAC 不在清單中")
                else:
                    results.add_pass(cat, f"{mid}-成員一致", "所有成員 MAC 都在清單中")

            # 測試 2: VersionRecord 的 hostname 必須在設備清單中
            device_stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == mid
            )
            device_result = await session.execute(device_stmt)
            devices = device_result.scalars().all()
            valid_hostnames = set()
            for d in devices:
                if d.old_hostname:
                    valid_hostnames.add(d.old_hostname.upper())
                if d.new_hostname:
                    valid_hostnames.add(d.new_hostname.upper())

            version_stmt = select(VersionRecord.switch_hostname).where(
                VersionRecord.maintenance_id == mid
            ).distinct()
            version_result = await session.execute(version_stmt)
            version_hostnames = {row[0].upper() for row in version_result.fetchall() if row[0]}

            invalid_hosts = version_hostnames - valid_hostnames
            if invalid_hosts and valid_hostnames:
                results.add_warning(
                    cat,
                    f"{mid}-版本hostname",
                    f"{len(invalid_hosts)} 個 hostname 不在設備清單中"
                )
            else:
                results.add_pass(cat, f"{mid}-版本hostname一致", "所有 hostname 都在設備清單中")

            # 測試 3: VersionExpectation 的 hostname 必須在設備清單中
            exp_stmt = select(VersionExpectation.hostname).where(
                VersionExpectation.maintenance_id == mid
            )
            exp_result = await session.execute(exp_stmt)
            exp_hostnames = {row[0].upper() for row in exp_result.fetchall() if row[0]}

            invalid_exp = exp_hostnames - valid_hostnames
            if invalid_exp and valid_hostnames:
                results.add_warning(
                    cat,
                    f"{mid}-期望hostname",
                    f"{len(invalid_exp)} 個期望的 hostname 不在設備清單中"
                )
            else:
                results.add_pass(cat, f"{mid}-期望hostname一致", "所有期望 hostname 都在設備清單中")


# =============================================================================
# 10. 並發和性能測試
# =============================================================================
async def test_concurrent_requests():
    """測試並發請求處理"""
    print("\n📋 [10] 並發請求測試...")
    cat = "並發測試"

    import httpx
    import time

    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # 並發請求 10 個相同的 API
        start_time = time.time()

        tasks = []
        for i in range(10):
            task = client.get(
                f"{base_url}/comparisons/checkpoints/2026-PING-TEST/summaries",
                params={"include_categories": "true"},
                timeout=30,
            )
            tasks.append(task)

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        error_count = sum(1 for r in responses if isinstance(r, Exception))

        if success_count == 10:
            results.add_pass(cat, "10並發-summaries", f"全部成功，耗時 {elapsed:.2f}s")
        else:
            results.add_fail(cat, "10並發-summaries", "10 成功", f"{success_count} 成功, {error_count} 錯誤")

        # 測試不同 API 的並發
        mixed_tasks = [
            client.get(f"{base_url}/comparisons/checkpoints/2026-PING-TEST/summaries", timeout=30),
            client.get(f"{base_url}/dashboard/maintenance/2026-PING-TEST/summary", timeout=30),
            client.get(f"{base_url}/comparisons/checkpoints/2026-PING-TEST/summaries", params={"include_categories": "true"}, timeout=30),
        ]

        mixed_responses = await asyncio.gather(*mixed_tasks, return_exceptions=True)
        mixed_success = sum(1 for r in mixed_responses if not isinstance(r, Exception) and r.status_code == 200)

        if mixed_success == 3:
            results.add_pass(cat, "混合並發", "全部成功")
        else:
            results.add_fail(cat, "混合並發", 3, mixed_success)


# =============================================================================
# Main
# =============================================================================
async def main():
    """主測試函數"""
    print("=" * 100)
    print("                         開始綜合測試 V2")
    print("=" * 100)

    try:
        await test_multiple_maintenances()
        await test_comparison_logic_deep()
        await test_severity_calculation()
        await test_severity_override_complete()
        await test_category_cross_validation()
        await test_trend_data_integrity()
        await test_dashboard_math_logic()
        await test_edge_cases_complete()
        await test_data_consistency_deep()
        await test_concurrent_requests()
    except Exception as e:
        import traceback
        results.add_fail("測試執行", "成功完成", str(e), traceback.format_exc())

    print("\n")
    print(results.summary())

    # 輸出到檔案
    with open("/Users/coolguazi/Project/ClineTest/network_dashboard/tests/test_report_v2.txt", "w") as f:
        f.write(results.summary())

    print(f"\n報告已儲存到: tests/test_report_v2.txt")

    return len(results.failed) == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
