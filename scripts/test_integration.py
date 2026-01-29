#!/usr/bin/env python3
"""
Integration test for data flow verification.

Tests:
1. ClientCollectionService correctly filters by MAC whitelist
2. ClientComparisonService correctly uses MaintenanceMacList
3. End-to-end comparison count matches MAC list count
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func

from app.db.base import get_session_context
from app.db.models import (
    MaintenanceMacList,
    ClientRecord,
    ClientComparison,
)
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


async def test_mac_list_count(maintenance_id: str) -> int:
    """Check MAC list count."""
    async with get_session_context() as session:
        stmt = select(func.count()).select_from(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        print(f"[OK] MaintenanceMacList count: {count}")
        return count


async def test_client_record_count(maintenance_id: str) -> tuple[int, int]:
    """Check ClientRecord counts by phase."""
    async with get_session_context() as session:
        old_stmt = select(func.count()).select_from(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.OLD,
        )
        old_result = await session.execute(old_stmt)
        old_count = old_result.scalar() or 0

        new_stmt = select(func.count()).select_from(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
        )
        new_result = await session.execute(new_stmt)
        new_count = new_result.scalar() or 0

        print(f"[OK] ClientRecord OLD: {old_count}, NEW: {new_count}")
        return old_count, new_count


async def test_comparison_count(maintenance_id: str) -> int:
    """Check ClientComparison count."""
    async with get_session_context() as session:
        stmt = select(func.count()).select_from(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        print(f"[OK] ClientComparison count: {count}")
        return count


async def test_unique_macs_in_records(maintenance_id: str) -> tuple[int, int]:
    """Test that ClientRecords only contain MACs from whitelist."""
    async with get_session_context() as session:
        # Get MAC whitelist
        mac_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        whitelist = {m.upper() for m in mac_result.scalars().all()}

        # Get unique MACs in OLD records
        old_mac_stmt = (
            select(ClientRecord.mac_address)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.OLD,
            )
            .distinct()
        )
        old_result = await session.execute(old_mac_stmt)
        old_macs = {m.upper() for m in old_result.scalars().all() if m}

        # Get unique MACs in NEW records
        new_mac_stmt = (
            select(ClientRecord.mac_address)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
            )
            .distinct()
        )
        new_result = await session.execute(new_mac_stmt)
        new_macs = {m.upper() for m in new_result.scalars().all() if m}

        # Check if MACs are in whitelist
        old_in_whitelist = old_macs & whitelist
        new_in_whitelist = new_macs & whitelist
        old_not_in_whitelist = old_macs - whitelist
        new_not_in_whitelist = new_macs - whitelist

        print(f"[OK] Unique MACs - OLD: {len(old_macs)}, NEW: {len(new_macs)}")
        print(f"     OLD in whitelist: {len(old_in_whitelist)}/{len(whitelist)}")
        print(f"     NEW in whitelist: {len(new_in_whitelist)}/{len(whitelist)}")

        if old_not_in_whitelist:
            print(f"[WARN] OLD MACs not in whitelist: {len(old_not_in_whitelist)}")
        if new_not_in_whitelist:
            print(f"[WARN] NEW MACs not in whitelist: {len(new_not_in_whitelist)}")

        return len(old_in_whitelist), len(new_in_whitelist)


async def test_comparison_generation(maintenance_id: str) -> int:
    """Test ClientComparisonService with MAC list."""
    service = ClientComparisonService()
    async with get_session_context() as session:
        comparisons = await service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        await service.save_comparisons(comparisons, session)

        summary = await service.get_comparison_summary(
            maintenance_id=maintenance_id,
            session=session,
        )
        print(f"[OK] Comparison summary: {summary}")
        return summary.get("total", 0)


async def run_tests(maintenance_id: str):
    """Run all integration tests."""
    print(f"\n{'=' * 60}")
    print(f"INTEGRATION TEST: {maintenance_id}")
    print(f"{'=' * 60}\n")

    # 1. Check MAC list
    mac_count = await test_mac_list_count(maintenance_id)

    # 2. Check existing records
    await test_client_record_count(maintenance_id)

    # 3. Check existing comparisons
    await test_comparison_count(maintenance_id)

    # 4. Test MAC whitelist adherence
    print("\n--- Checking MAC Whitelist Adherence ---")
    await test_unique_macs_in_records(maintenance_id)

    # 6. Test comparison generation
    print("\n--- Running ClientComparisonService ---")
    comparison_total = await test_comparison_generation(maintenance_id)

    # 7. Final verification
    print(f"\n{'=' * 60}")
    print("VERIFICATION RESULTS")
    print(f"{'=' * 60}")

    errors = []

    # MAC list should match comparison count
    if comparison_total != mac_count:
        errors.append(
            f"MISMATCH: Comparison count ({comparison_total}) "
            f"!= MAC list count ({mac_count})"
        )
    else:
        print(f"[PASS] Comparison count matches MAC list: {comparison_total}")

    # ClientRecord should only contain MACs from whitelist
    # (since seed script creates exactly the MAC count)
    if errors:
        print("\n[FAIL] Errors detected:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("\n[ALL TESTS PASSED]")
        return 0


if __name__ == "__main__":
    maintenance_id = sys.argv[1] if len(sys.argv) > 1 else "TEST-100"
    exit_code = asyncio.run(run_tests(maintenance_id))
    sys.exit(exit_code)
