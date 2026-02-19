#!/usr/bin/env python3
"""
Single collection cycle against real DB.

Uses ConfiguredFetcher to call external API (or Mock API Server),
then writes results to the real DB configured in .env.

用途：在公司環境驗證完整的 fetch → parse → DB 流程。

Usage:
    # 前提：.env 已設定 DB 連線，且 DB 中有 is_active=True 的歲修 + 設備清單

    python scripts/collect_once.py                     # 對所有 active 歲修跑一輪
    python scripts/collect_once.py --mid TEST-001      # 只跑指定歲修
    python scripts/collect_once.py --api get_fan       # 只跑指定 API
    python scripts/collect_once.py --seed              # 自動種入測試歲修 + 設備

快速開始（完全從零）:
    python scripts/collect_once.py --seed              # 種入 + 跑一輪 + 看結果
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("collect_once")


async def seed_test_data() -> str:
    """Seed a test maintenance with 3 devices (HPE, IOS, NXOS)."""
    from app.db.base import get_session_context
    from app.db.models import MaintenanceConfig, MaintenanceDeviceList
    from sqlalchemy import select

    test_mid = "COLLECT-TEST"

    async with get_session_context() as session:
        # Check if already exists
        existing = await session.execute(
            select(MaintenanceConfig).where(
                MaintenanceConfig.maintenance_id == test_mid
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Test maintenance '%s' already exists, reusing", test_mid)
            # Ensure active
            config = (await session.execute(
                select(MaintenanceConfig).where(
                    MaintenanceConfig.maintenance_id == test_mid
                )
            )).scalar_one()
            config.is_active = True
            await session.commit()
            return test_mid

        # Create maintenance
        session.add(MaintenanceConfig(
            maintenance_id=test_mid,
            name="Collection Pipeline Test",
            is_active=True,
        ))

        # Add test devices (3 vendor types)
        devices = [
            {
                "old_hostname": "SW-TEST-HPE-01",
                "old_ip_address": "10.0.10.1",
                "old_vendor": "HPE",
                "new_hostname": "SW-TEST-HPE-01",
                "new_ip_address": "10.0.10.1",
                "new_vendor": "HPE",
            },
            {
                "old_hostname": "SW-TEST-IOS-01",
                "old_ip_address": "10.0.20.1",
                "old_vendor": "Cisco-IOS",
                "new_hostname": "SW-TEST-IOS-01",
                "new_ip_address": "10.0.20.1",
                "new_vendor": "Cisco-IOS",
            },
            {
                "old_hostname": "SW-TEST-NXOS-01",
                "old_ip_address": "10.0.30.1",
                "old_vendor": "Cisco-NXOS",
                "new_hostname": "SW-TEST-NXOS-01",
                "new_ip_address": "10.0.30.1",
                "new_vendor": "Cisco-NXOS",
            },
        ]

        for d in devices:
            session.add(MaintenanceDeviceList(maintenance_id=test_mid, **d))

        await session.commit()
        logger.info(
            "Seeded maintenance '%s' with %d devices",
            test_mid, len(devices),
        )

    return test_mid


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run one collection cycle")
    parser.add_argument("--mid", help="Maintenance ID (default: all active)")
    parser.add_argument("--api", help="Only run specific API (e.g. get_fan)")
    parser.add_argument(
        "--seed", action="store_true",
        help="Seed test maintenance + devices before collecting",
    )
    args = parser.parse_args()

    # ── 1. Init DB ──────────────────────────────────────────────
    from app.db.base import init_db

    await init_db()
    logger.info("DB connected")

    # ── 2. Discover parsers ─────────────────────────────────────
    from app.parsers.registry import auto_discover_parsers

    count = auto_discover_parsers()
    logger.info("Discovered %d parser modules", count)

    # ── 3. Setup fetchers ───────────────────────────────────────
    from app.fetchers.registry import setup_fetchers
    from app.main import load_fetcher_config

    fetcher_config = load_fetcher_config()
    setup_fetchers(
        fetcher_configs=fetcher_config.get("fetchers"),
    )
    logger.info("Fetchers registered")

    # ── 4. Seed if requested ────────────────────────────────────
    if args.seed:
        test_mid = await seed_test_data()
        if not args.mid:
            args.mid = test_mid

    # ── 5. Determine maintenance IDs ────────────────────────────
    if args.mid:
        maintenance_ids = [args.mid]
    else:
        from sqlalchemy import select
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig

        async with get_session_context() as session:
            result = await session.execute(
                select(MaintenanceConfig.maintenance_id).where(
                    MaintenanceConfig.is_active == True  # noqa: E712
                )
            )
            maintenance_ids = [row[0] for row in result.fetchall()]

    if not maintenance_ids:
        logger.error("No active maintenances found. Use --seed to create one.")
        sys.exit(1)

    logger.info("Target maintenances: %s", maintenance_ids)

    # ── 6. Determine APIs to run ────────────────────────────────
    import yaml

    with open("config/scheduler.yaml") as f:
        cfg = yaml.safe_load(f)

    api_configs = cfg.get("fetchers", {})

    if args.api:
        if args.api not in api_configs:
            logger.error("Unknown API '%s'. Available: %s", args.api, list(api_configs.keys()))
            sys.exit(1)
        api_configs = {args.api: api_configs[args.api]}

    # ── 7. Run collection ───────────────────────────────────────
    from app.services.data_collection import ApiCollectionService

    svc = ApiCollectionService()
    all_results: list[dict] = []

    for mid in maintenance_ids:
        for api_name, api_cfg in api_configs.items():
            source = api_cfg.get("source", "")
            try:
                result = await svc.collect(
                    api_name=api_name,
                    source=source,
                    maintenance_id=mid,
                )
                all_results.append({
                    "mid": mid,
                    "api": api_name,
                    "status": "OK",
                    "total": result["total"],
                    "success": result["success"],
                    "failed": result["failed"],
                })
            except Exception as e:
                all_results.append({
                    "mid": mid,
                    "api": api_name,
                    "status": "ERROR",
                    "error": str(e),
                })

    # ── 8. Print summary ────────────────────────────────────────
    print()
    print("=" * 72)
    print("Collection Results")
    print("=" * 72)

    ok = 0
    fail = 0
    for r in all_results:
        if r["status"] == "OK":
            ok += 1
            print(
                f"  OK   {r['mid']:<18} {r['api']:<22} "
                f"{r['success']}/{r['total']} devices"
            )
        else:
            fail += 1
            print(
                f"  FAIL {r['mid']:<18} {r['api']:<22} "
                f"{r['error']}"
            )

    print("-" * 72)
    print(f"  {ok} OK, {fail} FAIL")
    print("=" * 72)

    # ── 9. Show DB record counts ────────────────────────────────
    from sqlalchemy import select, func
    from app.db.base import get_session_context
    from app.db.models import CollectionBatch

    async with get_session_context() as session:
        for mid in maintenance_ids:
            result = await session.execute(
                select(
                    CollectionBatch.collection_type,
                    func.count(CollectionBatch.id),
                ).where(
                    CollectionBatch.maintenance_id == mid,
                ).group_by(
                    CollectionBatch.collection_type,
                )
            )
            rows = result.fetchall()
            if rows:
                print(f"\n  DB batches for '{mid}':")
                for ctype, cnt in sorted(rows):
                    print(f"    {ctype:<22} {cnt} batches")

    # ── 10. Close DB ────────────────────────────────────────────
    from app.db.base import close_db

    await close_db()

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
