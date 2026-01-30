#!/usr/bin/env python3
"""
整合測試：驗證資料流完整性。

測試 Mock 資料生成器和整體資料流是否運作正常。
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func

from app.db.base import get_session_context
from app.db.models import ClientRecord, MaintenanceMacList
from app.services.mock_data_generator import get_mock_data_generator
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


async def test_mock_data_generator(maintenance_id: str) -> int:
    """測試 MockDataGenerator 生成功能。"""
    print("\n1. 測試 MockDataGenerator...")

    generator = get_mock_data_generator()

    async with get_session_context() as session:
        # 檢查 MAC 清單是否存在
        mac_stmt = select(func.count()).select_from(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        mac_count = mac_result.scalar() or 0

        if mac_count == 0:
            print(f"   [WARN] 無 MAC 清單，請先執行 seed 腳本")
            return 0

        print(f"   - MAC 清單數量: {mac_count}")

        # 生成新記錄（從 MAC 清單）
        records = await generator.generate_client_records(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
            session=session,
            base_records=None,  # 首次生成，不基於現有記錄
        )

        # 儲存記錄
        for r in records:
            session.add(r)
        await session.commit()

        print(f"   ✓ 生成 {len(records)} 筆新記錄")

        # 驗證記錄數量
        if len(records) != mac_count:
            print(f"   [WARN] 記錄數 ({len(records)}) != MAC 清單數 ({mac_count})")

        return len(records)


async def test_varied_record_generation(maintenance_id: str) -> int:
    """測試基於現有記錄生成變化版本。"""
    print("\n2. 測試變化記錄生成...")

    generator = get_mock_data_generator()

    async with get_session_context() as session:
        # 獲取最新的 NEW 階段記錄
        subquery = (
            select(func.max(ClientRecord.collected_at))
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
            )
            .scalar_subquery()
        )

        stmt = select(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
            ClientRecord.collected_at == subquery,
        )
        result = await session.execute(stmt)
        latest_records = list(result.scalars().all())

        if not latest_records:
            print("   [WARN] 無現有記錄，跳過變化測試")
            return 0

        print(f"   - 基準記錄數: {len(latest_records)}")

        # 生成變化版本
        varied_records = await generator.generate_client_records(
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
            session=session,
            base_records=latest_records,
        )

        # 儲存記錄
        for r in varied_records:
            session.add(r)
        await session.commit()

        print(f"   ✓ 生成 {len(varied_records)} 筆變化記錄")

        # 檢查是否有變化
        changes = 0
        for base, varied in zip(latest_records, varied_records):
            if (
                base.speed != varied.speed or
                base.duplex != varied.duplex or
                base.link_status != varied.link_status or
                base.ping_reachable != varied.ping_reachable or
                base.interface_name != varied.interface_name
            ):
                changes += 1

        print(f"   - 有變化的記錄: {changes}/{len(varied_records)}")

        return len(varied_records)


async def test_timepoints_retrieval(maintenance_id: str) -> int:
    """測試時間點取得功能（7天限制）。"""
    print("\n3. 測試時間點取得（7天限制）...")

    service = ClientComparisonService()

    async with get_session_context() as session:
        timepoints = await service.get_timepoints(
            maintenance_id=maintenance_id,
            session=session,
            max_days=7,
        )

        print(f"   ✓ 取得 {len(timepoints)} 個時間點")

        if timepoints:
            first = timepoints[0]
            last = timepoints[-1]
            print(f"   - 最早: {first.get('label', 'N/A')}")
            print(f"   - 最新: {last.get('label', 'N/A')}")

        return len(timepoints)


async def test_statistics_generation(maintenance_id: str) -> int:
    """測試統計資料生成（每小時採樣）。"""
    print("\n4. 測試統計資料生成（每小時採樣）...")

    service = ClientComparisonService()

    async with get_session_context() as session:
        stats = await service.get_statistics(
            maintenance_id=maintenance_id,
            session=session,
            max_days=7,
            hourly_sampling=True,
        )

        print(f"   ✓ 取得 {len(stats)} 個採樣點的統計")

        if stats:
            latest = stats[-1]
            print(f"   - 最新時間點: {latest.get('label', 'N/A')}")
            print(f"   - 總數: {latest.get('total', 0)}")
            print(f"   - 異常: {latest.get('has_issues', 0)}")
            print(f"   - Critical: {latest.get('critical', 0)}")
            print(f"   - Warning: {latest.get('warning', 0)}")

        # 檢查採樣數量是否合理（最多 168 個）
        if len(stats) > 168:
            print(f"   [WARN] 採樣點數量 ({len(stats)}) 超過預期最大值 (168)")

        return len(stats)


async def test_comparison_generation(maintenance_id: str) -> dict:
    """測試比較結果生成。"""
    print("\n5. 測試比較結果生成...")

    service = ClientComparisonService()

    async with get_session_context() as session:
        comparisons = await service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )

        print(f"   ✓ 生成 {len(comparisons)} 筆比較結果")

        # 統計 severity 分布
        severities = {"critical": 0, "warning": 0, "info": 0}
        changed = 0

        for c in comparisons:
            if c.severity in severities:
                severities[c.severity] += 1
            if c.is_changed:
                changed += 1

        print(f"   - Severity 分布: {severities}")
        print(f"   - 有變化的記錄: {changed}/{len(comparisons)}")

        return {
            "total": len(comparisons),
            "changed": changed,
            "severities": severities,
        }


async def run_tests(maintenance_id: str):
    """執行所有測試。"""
    print(f"\n{'=' * 60}")
    print(f"資料流測試: {maintenance_id}")
    print(f"時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'=' * 60}")

    results = {}
    errors = []

    try:
        # 1. 測試 Mock 資料生成
        results["mock_records"] = await test_mock_data_generator(maintenance_id)

        # 2. 測試變化記錄生成
        results["varied_records"] = await test_varied_record_generation(maintenance_id)

        # 3. 測試時間點取得
        results["timepoints"] = await test_timepoints_retrieval(maintenance_id)

        # 4. 測試統計資料
        results["statistics"] = await test_statistics_generation(maintenance_id)

        # 5. 測試比較結果
        results["comparisons"] = await test_comparison_generation(maintenance_id)

    except Exception as e:
        errors.append(f"測試失敗: {e}")
        import traceback
        traceback.print_exc()

    # 結果摘要
    print(f"\n{'=' * 60}")
    print("測試結果摘要")
    print(f"{'=' * 60}")

    if results.get("mock_records", 0) > 0:
        print(f"✓ Mock 資料生成: {results['mock_records']} 筆")
    else:
        errors.append("Mock 資料生成失敗或無資料")

    if results.get("varied_records", 0) > 0:
        print(f"✓ 變化記錄生成: {results['varied_records']} 筆")

    if results.get("timepoints", 0) > 0:
        print(f"✓ 時間點取得: {results['timepoints']} 個")
    else:
        print("⚠ 時間點取得: 無資料")

    if results.get("statistics", 0) > 0:
        print(f"✓ 統計採樣點: {results['statistics']} 個")

    if results.get("comparisons"):
        comp = results["comparisons"]
        print(f"✓ 比較結果: {comp['total']} 筆 (變化: {comp['changed']})")

    if errors:
        print(f"\n[ERRORS]")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{'=' * 60}")
    print("[所有測試通過]")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    maintenance_id = sys.argv[1] if len(sys.argv) > 1 else "TEST-100"
    exit_code = asyncio.run(run_tests(maintenance_id))
    sys.exit(exit_code)
