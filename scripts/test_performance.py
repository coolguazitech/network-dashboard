#!/usr/bin/env python3
"""
效能測試：驗證大量資料處理。

測試系統在接近 Production 負載下的效能表現。
"""
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, delete

from app.db.base import get_session_context
from app.db.models import ClientRecord, MaintenanceMacList
from app.services.mock_data_generator import get_mock_data_generator
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


async def measure_batch_generation(
    maintenance_id: str,
    batch_count: int = 10,
) -> dict:
    """測試批量資料生成效能。"""
    print(f"\n1. 批量生成測試 ({batch_count} 批次)...")

    generator = get_mock_data_generator()
    total_records = 0
    times = []

    async with get_session_context() as session:
        # 獲取 MAC 清單數量
        mac_stmt = select(func.count()).select_from(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        mac_count = mac_result.scalar() or 0

        if mac_count == 0:
            print("   [WARN] 無 MAC 清單，跳過測試")
            return {"total_records": 0, "avg_time": 0}

        print(f"   - MAC 清單數量: {mac_count}")
        print(f"   - 預期總記錄數: {mac_count * batch_count}")

        base_records = None

        for i in range(batch_count):
            start = time.time()

            records = await generator.generate_client_records(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.NEW,
                session=session,
                base_records=base_records,
            )

            for r in records:
                session.add(r)
            await session.commit()

            elapsed = time.time() - start
            times.append(elapsed)
            total_records += len(records)

            # 使用剛生成的記錄作為下一批的基準
            base_records = records

            if (i + 1) % 5 == 0:
                print(f"   - 批次 {i + 1}/{batch_count} 完成 ({elapsed:.3f}s)")

    avg_time = sum(times) / len(times) if times else 0
    total_time = sum(times)

    print(f"   ✓ 完成，共 {total_records} 筆記錄")
    print(f"   - 總耗時: {total_time:.2f} 秒")
    print(f"   - 平均每批: {avg_time:.3f} 秒")
    print(f"   - 每秒記錄數: {total_records / total_time:.1f}")

    return {
        "total_records": total_records,
        "total_time": total_time,
        "avg_time": avg_time,
        "records_per_second": total_records / total_time if total_time > 0 else 0,
    }


async def measure_timepoints_query(maintenance_id: str) -> dict:
    """測試時間點查詢效能。"""
    print("\n2. 時間點查詢效能測試...")

    service = ClientComparisonService()

    times = []
    for _ in range(5):  # 執行 5 次取平均
        start = time.time()
        async with get_session_context() as session:
            timepoints = await service.get_timepoints(
                maintenance_id=maintenance_id,
                session=session,
                max_days=7,
            )
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    tp_count = len(timepoints) if timepoints else 0

    print(f"   ✓ 取得 {tp_count} 個時間點")
    print(f"   - 平均查詢時間: {avg_time:.3f} 秒")

    return {
        "timepoint_count": tp_count,
        "avg_query_time": avg_time,
    }


async def measure_statistics_calculation(maintenance_id: str) -> dict:
    """測試統計計算效能。"""
    print("\n3. 統計計算效能測試...")

    service = ClientComparisonService()

    times = []
    for _ in range(3):  # 執行 3 次取平均
        start = time.time()
        async with get_session_context() as session:
            stats = await service.get_statistics(
                maintenance_id=maintenance_id,
                session=session,
                max_days=7,
                hourly_sampling=True,
            )
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    stats_count = len(stats) if stats else 0

    print(f"   ✓ 計算 {stats_count} 個採樣點的統計")
    print(f"   - 平均計算時間: {avg_time:.3f} 秒")

    return {
        "stats_count": stats_count,
        "avg_calc_time": avg_time,
    }


async def measure_comparison_generation(maintenance_id: str) -> dict:
    """測試比較結果生成效能。"""
    print("\n4. 比較結果生成效能測試...")

    service = ClientComparisonService()

    times = []
    for _ in range(3):  # 執行 3 次取平均
        start = time.time()
        async with get_session_context() as session:
            comparisons = await service.generate_comparisons(
                maintenance_id=maintenance_id,
                session=session,
            )
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    comp_count = len(comparisons) if comparisons else 0

    print(f"   ✓ 生成 {comp_count} 筆比較結果")
    print(f"   - 平均生成時間: {avg_time:.3f} 秒")

    return {
        "comparison_count": comp_count,
        "avg_gen_time": avg_time,
    }


async def measure_record_count(maintenance_id: str) -> dict:
    """測量現有記錄數量。"""
    print("\n0. 現有資料統計...")

    async with get_session_context() as session:
        # 總記錄數
        total_stmt = select(func.count()).select_from(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id
        )
        total_result = await session.execute(total_stmt)
        total_count = total_result.scalar() or 0

        # NEW 階段記錄數
        new_stmt = select(func.count()).select_from(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
        )
        new_result = await session.execute(new_stmt)
        new_count = new_result.scalar() or 0

        # 時間點數量
        tp_stmt = (
            select(func.count(func.distinct(ClientRecord.collected_at)))
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
            )
        )
        tp_result = await session.execute(tp_stmt)
        tp_count = tp_result.scalar() or 0

    print(f"   - 總 ClientRecord: {total_count}")
    print(f"   - NEW 階段記錄: {new_count}")
    print(f"   - 時間點數量: {tp_count}")

    return {
        "total_records": total_count,
        "new_records": new_count,
        "timepoint_count": tp_count,
    }


async def cleanup_test_data(maintenance_id: str, keep_latest: int = 10):
    """清理測試資料，保留最新 N 個時間點。"""
    print(f"\n清理測試資料（保留最新 {keep_latest} 個時間點）...")

    async with get_session_context() as session:
        # 獲取要保留的時間點
        keep_stmt = (
            select(func.distinct(ClientRecord.collected_at))
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
            )
            .order_by(ClientRecord.collected_at.desc())
            .limit(keep_latest)
        )
        keep_result = await session.execute(keep_stmt)
        keep_times = list(keep_result.scalars().all())

        if not keep_times:
            print("   - 無資料需要清理")
            return

        oldest_to_keep = min(keep_times)

        # 刪除舊資料
        del_stmt = delete(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
            ClientRecord.collected_at < oldest_to_keep,
        )
        result = await session.execute(del_stmt)
        await session.commit()

        deleted = result.rowcount or 0
        print(f"   ✓ 刪除 {deleted} 筆舊記錄")


async def run_performance_tests(
    maintenance_id: str,
    batch_count: int = 10,
    cleanup: bool = True,
):
    """執行效能測試。"""
    print(f"\n{'=' * 60}")
    print(f"效能測試: {maintenance_id}")
    print(f"時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'=' * 60}")

    results = {}

    try:
        # 0. 現有資料統計
        results["existing"] = await measure_record_count(maintenance_id)

        # 1. 批量生成測試
        results["batch_gen"] = await measure_batch_generation(
            maintenance_id, batch_count
        )

        # 2. 時間點查詢效能
        results["timepoints"] = await measure_timepoints_query(maintenance_id)

        # 3. 統計計算效能
        results["statistics"] = await measure_statistics_calculation(maintenance_id)

        # 4. 比較結果生成效能
        results["comparisons"] = await measure_comparison_generation(maintenance_id)

        # 清理測試資料
        if cleanup:
            await cleanup_test_data(maintenance_id, keep_latest=10)

    except Exception as e:
        print(f"\n[ERROR] 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 結果摘要
    print(f"\n{'=' * 60}")
    print("效能測試結果摘要")
    print(f"{'=' * 60}")

    batch = results.get("batch_gen", {})
    tp = results.get("timepoints", {})
    stats = results.get("statistics", {})
    comp = results.get("comparisons", {})

    print(f"\n批量生成:")
    print(f"  - 總記錄數: {batch.get('total_records', 0)}")
    print(f"  - 每秒記錄: {batch.get('records_per_second', 0):.1f}")

    print(f"\n查詢效能:")
    print(f"  - 時間點查詢: {tp.get('avg_query_time', 0):.3f}s ({tp.get('timepoint_count', 0)} 個)")
    print(f"  - 統計計算: {stats.get('avg_calc_time', 0):.3f}s ({stats.get('stats_count', 0)} 個採樣點)")
    print(f"  - 比較生成: {comp.get('avg_gen_time', 0):.3f}s ({comp.get('comparison_count', 0)} 筆)")

    # 效能判斷
    print(f"\n{'=' * 60}")
    warnings = []

    if batch.get("records_per_second", 0) < 100:
        warnings.append("批量生成速度較慢 (< 100 records/s)")

    if tp.get("avg_query_time", 0) > 1.0:
        warnings.append("時間點查詢較慢 (> 1s)")

    if stats.get("avg_calc_time", 0) > 5.0:
        warnings.append("統計計算較慢 (> 5s)")

    if comp.get("avg_gen_time", 0) > 3.0:
        warnings.append("比較生成較慢 (> 3s)")

    if warnings:
        print("[效能警告]")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("[效能良好]")

    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="效能測試")
    parser.add_argument(
        "maintenance_id",
        nargs="?",
        default="TEST-100",
        help="歲修 ID (預設: TEST-100)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=10,
        help="批次數量 (預設: 10)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="不清理測試資料",
    )

    args = parser.parse_args()

    exit_code = asyncio.run(
        run_performance_tests(
            maintenance_id=args.maintenance_id,
            batch_count=args.batch,
            cleanup=not args.no_cleanup,
        )
    )
    sys.exit(exit_code)
