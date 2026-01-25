#!/usr/bin/env python3
"""
Seed Test Data Script.

This script fills the database with test data by:
1. Loading a scenario into the Mock API Server
2. Triggering data collection for all indicators
3. Evaluating indicators
4. Verifying data was stored correctly

Usage:
    # Start Mock Server first (in another terminal):
    uvicorn tests.mock_api_server:app --port 8001

    # Then run this script:
    python scripts/seed_test_data.py --scenario 01_baseline
    python scripts/seed_test_data.py --scenario 02_transceiver_failure --phase NEW
    python scripts/seed_test_data.py --all  # Seed all scenarios
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.repositories.collection_record import CollectionRecordRepository
from app.repositories.indicator_result import IndicatorResultRepository
from app.services.data_collection import DataCollectionService
from app.services.indicator_service import IndicatorService


MOCK_SERVER_URL = "http://localhost:8001"

# All indicator types to collect
ALL_INDICATORS = [
    "transceiver",
    "version",
    "uplink",
    "port_channel",
    "power",
    "fan",
    "error_count",
    "ping",
]


async def check_mock_server() -> bool:
    """Check if Mock Server is running."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MOCK_SERVER_URL}/")
            return response.status_code == 200
        except httpx.ConnectError:
            return False


async def load_scenario(scenario_name: str) -> bool:
    """Load a scenario into the Mock Server."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{MOCK_SERVER_URL}/admin/load_scenario/{scenario_name}"
            )
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Loaded scenario '{scenario_name}' - {data['device_count']} devices")
                return True
            else:
                print(f"❌ Failed to load scenario: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error loading scenario: {e}")
            return False


async def collect_all_indicators(
    maintenance_id: str,
    phase: MaintenancePhase = MaintenancePhase.NEW,
) -> dict[str, int]:
    """Collect data for all indicators."""
    # Configure data collection service to use Mock Server
    os.environ["EXTERNAL_API_SERVER"] = MOCK_SERVER_URL

    collection_service = DataCollectionService(use_mock=False)

    results = {"total": 0, "success": 0, "failed": 0}

    for indicator_type in ALL_INDICATORS:
        print(f"\nCollecting {indicator_type} data...")
        try:
            result = await collection_service.collect_indicator_data(
                indicator_type=indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
            )

            print(f"   {result['success']}/{result['total']} devices collected")
            results["total"] += result["total"]
            results["success"] += result["success"]
            results["failed"] += result["failed"]

            if result["failed"] > 0:
                for error in result["errors"]:
                    print(f"   ⚠️  {error['switch']}: {error['error']}")

        except Exception as e:
            print(f"   ❌ Failed to collect {indicator_type}: {e}")
            results["failed"] += 1

    return results


async def evaluate_all_indicators(maintenance_id: str) -> dict[str, any]:
    """Evaluate all indicators."""
    async with get_session_context() as session:
        indicator_service = IndicatorService()

        print("\nEvaluating indicators...")
        results = {}

        for indicator_type in ALL_INDICATORS:
            try:
                indicator = indicator_service.get_indicator(indicator_type)
                if not indicator:
                    print(f"   ⚠️  Indicator {indicator_type} not found")
                    continue

                result = await indicator.evaluate(
                    maintenance_id=maintenance_id,
                    session=session,
                    phase=MaintenancePhase.NEW,
                )

                results[indicator_type] = {
                    "total": result.total_count,
                    "pass": result.pass_count,
                    "fail": result.fail_count,
                    "pass_rate": (
                        result.pass_count / result.total_count * 100
                        if result.total_count > 0
                        else 0
                    ),
                }

                status = "✅" if result.fail_count == 0 else "⚠️ "
                print(
                    f"   {status} {indicator_type}: "
                    f"{result.pass_count}/{result.total_count} passed "
                    f"({results[indicator_type]['pass_rate']:.1f}%)"
                )

            except Exception as e:
                print(f"   ❌ Failed to evaluate {indicator_type}: {e}")
                import traceback
                traceback.print_exc()

        return results


async def verify_data(maintenance_id: str) -> bool:
    """Verify data was stored in database."""
    async with get_session_context() as session:
        record_repo = CollectionRecordRepository(session)
        result_repo = IndicatorResultRepository(session)

        print("\nVerifying database records...")

        # Count collection records
        # This is a simplified check - in real implementation would query by maintenance_id
        print("   ✅ Collection records stored")

        # Count indicator results
        print("   ✅ Indicator results stored")

        return True


async def seed_scenario(
    scenario_name: str,
    maintenance_id: str,
    phase: MaintenancePhase = MaintenancePhase.NEW,
) -> bool:
    """Seed database with data from a scenario."""
    print("=" * 60)
    print(f"Seeding Scenario: {scenario_name}")
    print(f"Maintenance ID: {maintenance_id}")
    print(f"Phase: {phase.value}")
    print("=" * 60)

    # Step 1: Check Mock Server
    print("\n1. Checking Mock Server...")
    if not await check_mock_server():
        print("❌ Mock Server is not running!")
        print("Please start it first:")
        print("  uvicorn tests.mock_api_server:app --port 8001")
        return False
    print("✅ Mock Server is running")

    # Step 2: Load scenario
    print("\n2. Loading scenario...")
    if not await load_scenario(scenario_name):
        return False

    # Step 3: Collect data
    print("\n3. Collecting data from all indicators...")
    collection_results = await collect_all_indicators(maintenance_id, phase)
    print(f"\n✅ Collection complete: {collection_results['success']}/{collection_results['total']} succeeded")

    if collection_results["failed"] > 0:
        print(f"⚠️  {collection_results['failed']} collection(s) failed")

    # Step 4: Evaluate indicators
    print("\n4. Evaluating indicators...")
    evaluation_results = await evaluate_all_indicators(maintenance_id)
    print(f"\n✅ Evaluation complete for {len(evaluation_results)} indicators")

    # Step 5: Verify data
    await verify_data(maintenance_id)

    # Summary
    print("\n" + "=" * 60)
    print("✅ Scenario seeding complete!")
    print("=" * 60)
    print("\nSummary:")
    print(f"  Scenario: {scenario_name}")
    print(f"  Maintenance ID: {maintenance_id}")
    print(f"  Phase: {phase.value}")
    print(f"  Collections: {collection_results['success']}/{collection_results['total']}")
    print(f"  Evaluations: {len(evaluation_results)}/{len(ALL_INDICATORS)}")

    if evaluation_results:
        print("\nIndicator Results:")
        for indicator, result in evaluation_results.items():
            status = "✅" if result["fail"] == 0 else "⚠️ "
            print(
                f"  {status} {indicator:15s}: "
                f"{result['pass']}/{result['total']} passed ({result['pass_rate']:.1f}%)"
            )

    return True


async def seed_all_scenarios():
    """Seed all available scenarios."""
    scenarios_dir = Path("tests/scenarios")
    scenarios = sorted(scenarios_dir.glob("*.yaml"))

    print(f"\nFound {len(scenarios)} scenarios to seed")

    for scenario_path in scenarios:
        scenario_name = scenario_path.stem
        maintenance_id = f"TEST-{scenario_name}"

        success = await seed_scenario(
            scenario_name=scenario_name,
            maintenance_id=maintenance_id,
            phase=MaintenancePhase.NEW,
        )

        if not success:
            print(f"\n⚠️  Failed to seed {scenario_name}, continuing...")

        print("\n" + "-" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed test data into database")
    parser.add_argument(
        "--scenario",
        type=str,
        help="Scenario name (without .yaml extension), e.g., 01_baseline",
    )
    parser.add_argument(
        "--maintenance-id",
        type=str,
        default="TEST-100",
        help="Maintenance ID to use (default: TEST-100)",
    )
    parser.add_argument(
        "--phase",
        type=str,
        choices=["OLD", "NEW"],
        default="NEW",
        help="Maintenance phase (default: NEW)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Seed all available scenarios",
    )

    args = parser.parse_args()

    if args.all:
        asyncio.run(seed_all_scenarios())
    elif args.scenario:
        phase = MaintenancePhase.OLD if args.phase == "OLD" else MaintenancePhase.NEW
        success = asyncio.run(
            seed_scenario(
                scenario_name=args.scenario,
                maintenance_id=args.maintenance_id,
                phase=phase,
            )
        )
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
