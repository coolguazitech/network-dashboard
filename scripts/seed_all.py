#!/usr/bin/env python3
"""
Unified Seed Script for Network Dashboard.

Runs all seeding steps in order:
1. Generate factory scenario YAML files
2. Initialize DB (clean + create base data)
3. Seed 8 indicators with multi-round time series
4. Seed client records + comparisons (multi-round)

Prerequisites:
    Mock API server must be running on port 8001:
        uvicorn tests.mock_api_server:app --port 8001

Usage:
    python scripts/seed_all.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root and scripts dir to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from sqlalchemy import text, update

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context, init_db
from app.db.models import CollectionBatch
from app.repositories.indicator_result import IndicatorResultRepository
from app.services.data_collection import DataCollectionService
from app.services.indicator_service import IndicatorService

from factory_device_config import MAINTENANCE_ID

MOCK_SERVER_URL = "http://localhost:8001"

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

# Time series rounds for indicator data.
# Each round seeds the same baseline data, then backdates collected_at.
# This creates 3 time points visible in Dashboard charts.
INDICATOR_ROUNDS = [
    {"offset_hours": 6, "scenario": "factory_baseline"},
    {"offset_hours": 3, "scenario": "factory_baseline"},
    {"offset_hours": 0, "scenario": "factory_baseline"},  # latest = now
]


# ── Step 1: Generate Factory Scenarios ─────────────────────────


def step1_generate_scenarios():
    """Generate factory scenario YAML files."""
    print("\n" + "=" * 60)
    print("Step 1: Generating Factory Scenario YAML Files")
    print("=" * 60)

    from generate_factory_scenarios import main as gen_main
    gen_main()
    print("Done.")


# ── Step 2: Initialize DB ──────────────────────────────────────


async def step2_init_db():
    """Run init_factory_data to clean DB and create base data."""
    print("\n" + "=" * 60)
    print("Step 2: Initializing Database (Clean + Base Data)")
    print("=" * 60)

    from init_factory_data import main as init_main
    await init_main()
    print("Done.")


# ── Step 3: Seed Indicators (multi-round) ──────────────────────


async def _check_mock_server() -> bool:
    """Check if Mock Server is running."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MOCK_SERVER_URL}/")
            return response.status_code == 200
        except httpx.ConnectError:
            return False


async def _load_scenario(scenario_name: str) -> bool:
    """Load a scenario into the Mock Server."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{MOCK_SERVER_URL}/admin/load_scenario/{scenario_name}"
            )
            if response.status_code == 200:
                data = response.json()
                print(f"  Loaded scenario '{scenario_name}' "
                      f"- {data['device_count']} devices")
                return True
            else:
                print(f"  Failed to load scenario: {response.status_code}")
                return False
        except Exception as e:
            print(f"  Error loading scenario: {e}")
            return False


async def _collect_indicators(maintenance_id: str, phase: MaintenancePhase):
    """Collect data for all 8 indicators."""
    os.environ["EXTERNAL_API_SERVER"] = MOCK_SERVER_URL
    collection_service = DataCollectionService(use_mock=False)

    total_success = 0
    total_failed = 0

    for indicator_type in ALL_INDICATORS:
        try:
            result = await collection_service.collect_indicator_data(
                collection_type=indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
            )
            total_success += result["success"]
            total_failed += result["failed"]
            status = "OK" if result["failed"] == 0 else "PARTIAL"
            print(f"  {indicator_type:15s}: "
                  f"{result['success']}/{result['total']} ({status})")
        except Exception as e:
            total_failed += 1
            print(f"  {indicator_type:15s}: FAILED - {e}")

    return total_success, total_failed


async def _evaluate_indicators(maintenance_id: str):
    """Evaluate all 8 indicators."""
    async with get_session_context() as session:
        indicator_service = IndicatorService()

        for indicator_type in ALL_INDICATORS:
            try:
                indicator = indicator_service.get_indicator(indicator_type)
                if not indicator:
                    continue
                result = await indicator.evaluate(
                    maintenance_id=maintenance_id,
                    session=session,
                    phase=MaintenancePhase.NEW,
                )
                rate = (
                    result.pass_count / result.total_count * 100
                    if result.total_count > 0 else 0
                )
                print(f"  {indicator_type:15s}: "
                      f"{result.pass_count}/{result.total_count} "
                      f"({rate:.0f}%)")
            except Exception as e:
                print(f"  {indicator_type:15s}: EVAL FAILED - {e}")


async def _backdate_round(
    round_idx: int,
    target_time: datetime,
    maintenance_id: str,
):
    """
    Backdate collected_at for a round's collection data.

    After each collection round, all records have collected_at = now().
    We update them to the target time so the dashboard shows time series.

    Strategy: find the batches with the latest collected_at that haven't
    been backdated yet (they will be within the last minute), then update
    them and their typed records.
    """
    async with get_session_context() as session:
        # Find batches from this round (created within last 2 minutes)
        cutoff = datetime.utcnow() - timedelta(minutes=2)
        stmt = text("""
            UPDATE collection_batches
            SET collected_at = :target_time
            WHERE maintenance_id = :mid
              AND collected_at > :cutoff
        """)
        result = await session.execute(stmt, {
            "target_time": target_time,
            "mid": maintenance_id,
            "cutoff": cutoff,
        })
        batch_count = result.rowcount

        # Update all typed record tables
        typed_tables = [
            "transceiver_records",
            "version_records",
            "neighbor_records",
            "port_channel_records",
            "power_records",
            "fan_records",
            "interface_error_records",
            "ping_records",
            "indicator_results",
        ]
        for table_name in typed_tables:
            stmt = text(f"""
                UPDATE {table_name}
                SET collected_at = :target_time
                WHERE maintenance_id = :mid
                  AND collected_at > :cutoff
            """)
            try:
                await session.execute(stmt, {
                    "target_time": target_time,
                    "mid": maintenance_id,
                    "cutoff": cutoff,
                })
            except Exception:
                # indicator_results uses evaluated_at, not collected_at
                if table_name == "indicator_results":
                    stmt2 = text("""
                        UPDATE indicator_results
                        SET evaluated_at = :target_time
                        WHERE maintenance_id = :mid
                          AND evaluated_at > :cutoff
                    """)
                    await session.execute(stmt2, {
                        "target_time": target_time,
                        "mid": maintenance_id,
                        "cutoff": cutoff,
                    })

        await session.commit()
        print(f"  Backdated {batch_count} batches to "
              f"{target_time.strftime('%Y-%m-%d %H:%M')}")


async def step3_seed_indicators():
    """Seed 8 indicators with multi-round time series."""
    print("\n" + "=" * 60)
    print("Step 3: Seeding 8 Indicators (Multi-Round Time Series)")
    print("=" * 60)

    # Check mock server
    print("\nChecking Mock API Server...")
    if not await _check_mock_server():
        print("ERROR: Mock API Server is not running!")
        print("Please start it first:")
        print("  uvicorn tests.mock_api_server:app --port 8001")
        return False

    print("Mock API Server is running.\n")

    now = datetime.utcnow()

    for round_idx, round_cfg in enumerate(INDICATOR_ROUNDS):
        offset_h = round_cfg["offset_hours"]
        scenario = round_cfg["scenario"]
        target_time = now - timedelta(hours=offset_h)

        label = "latest" if offset_h == 0 else f"T-{offset_h}h"
        print(f"\n--- Round {round_idx + 1}/{len(INDICATOR_ROUNDS)} "
              f"({label}) ---")

        # Load scenario
        if not await _load_scenario(scenario):
            print("  Skipping round due to scenario load failure.")
            continue

        # Collect
        print("  Collecting:")
        success, failed = await _collect_indicators(
            MAINTENANCE_ID, MaintenancePhase.NEW,
        )
        print(f"  Total: {success} success, {failed} failed")

        # Evaluate
        print("  Evaluating:")
        await _evaluate_indicators(MAINTENANCE_ID)

        # Backdate timestamps (skip for latest round)
        if offset_h > 0:
            await _backdate_round(round_idx, target_time, MAINTENANCE_ID)

    print("\nIndicator seeding complete.")
    return True


# ── Step 4: Seed Client Data ──────────────────────────────────


async def step4_seed_clients():
    """Seed client records and comparisons."""
    print("\n" + "=" * 60)
    print("Step 4: Seeding Client Data (Multi-Round)")
    print("=" * 60)

    from seed_client_data import main as client_main
    await client_main()
    print("Done.")


# ── Main ──────────────────────────────────────────────────────


async def main():
    """Run all seeding steps."""
    print("=" * 60)
    print("Network Dashboard - Unified Seed")
    print(f"Maintenance ID: {MAINTENANCE_ID}")
    print("=" * 60)

    await init_db()

    # Step 1: Generate scenarios
    step1_generate_scenarios()

    # Step 2: Initialize DB
    await step2_init_db()

    # Step 3: Seed indicators
    ok = await step3_seed_indicators()
    if not ok:
        print("\nIndicator seeding failed. "
              "Client data will still be seeded.")

    # Step 4: Seed client data
    await step4_seed_clients()

    # Final summary
    print("\n" + "=" * 60)
    print("ALL SEEDING COMPLETE")
    print("=" * 60)
    print(f"\nMaintenance ID: {MAINTENANCE_ID}")
    print(f"Indicator rounds: {len(INDICATOR_ROUNDS)}")
    print("Client rounds: 3 (T-6h, T-3h, T-1h)")
    print("\nTo start the backend:")
    print("  uvicorn app.main:app --port 8000")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
