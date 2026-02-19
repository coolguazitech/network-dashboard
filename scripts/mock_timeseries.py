#!/usr/bin/env python3
"""
時間序列測試腳本。

用 raw test data + 真 parser + SQLite in-memory DB，
模擬多輪採集，驗證基準+變化點儲存策略（hash-based dedup）。

每輪使用相同 raw data → 驗證 hash dedup 正確跳過重複。
可搭配 --mutate 在某些輪次注入微小變化 → 驗證 change detection。

Usage:
    python scripts/mock_timeseries.py                    # 預設 10 輪
    python scripts/mock_timeseries.py --cycles 20        # 20 輪
    python scripts/mock_timeseries.py --interval 2       # 每 2 秒一輪
    python scripts/mock_timeseries.py --mutate 5         # 每 5 輪注入一次變化
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-5s  %(message)s",
)
logger = logging.getLogger("timeseries")

# Suppress noisy loggers
logging.getLogger("app.services.data_collection").setLevel(logging.WARNING)
logging.getLogger("app.fetchers").setLevel(logging.WARNING)
logging.getLogger("app.parsers").setLevel(logging.WARNING)

# Raw test data directory
RAW_DIR = Path("test_data/raw")

# Device type mapping: filename token → DeviceType enum value
DEVICE_TYPE_MAP = {
    "hpe": "HPE",
    "ios": "Cisco-IOS",
    "nxos": "Cisco-NXOS",
}


def _parse_raw_filename(filename: str) -> tuple[str, str, str] | None:
    """Parse raw filename into (api_name, device_type, ip) or None."""
    parts = Path(filename).stem.split("_")
    for i, part in enumerate(parts):
        if part in DEVICE_TYPE_MAP:
            api_name = "_".join(parts[:i])
            dt_str = parts[i]
            ip = ".".join(parts[i + 1:])
            return api_name, dt_str, ip
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Timeseries dedup test")
    parser.add_argument("--cycles", type=int, default=10, help="Number of collection cycles")
    parser.add_argument("--interval", type=float, default=2, help="Seconds between cycles")
    parser.add_argument("--mutate", type=int, default=0, help="Inject data mutation every N cycles (0=never)")
    args = parser.parse_args()

    # ── 1. Override DB to SQLite in-memory ──────────────────────
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite in-memory DB created (%d tables)", len(Base.metadata.tables))

    @asynccontextmanager
    async def mem_session():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ── 2. Discover parsers ──────────────────────────────────────
    from app.parsers.registry import auto_discover_parsers, parser_registry

    parser_registry.clear()
    auto_discover_parsers()
    logger.info("Discovered %d parsers", len(parser_registry.list_parsers()))

    # ── 3. Load scheduler.yaml ──────────────────────────────────
    import yaml

    with open("config/scheduler.yaml") as f:
        cfg = yaml.safe_load(f)

    api_configs = cfg.get("fetchers", {})
    logger.info("scheduler.yaml: %d APIs", len(api_configs))

    # ── 4. Load raw test data files ──────────────────────────────
    if not RAW_DIR.exists():
        logger.error("Raw test data directory not found: %s", RAW_DIR)
        sys.exit(1)

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    # Parse into usable entries
    test_entries: list[dict] = []
    for f in raw_files:
        parsed = _parse_raw_filename(f.name)
        if parsed is None:
            continue
        api_name, dt_str, ip = parsed
        if api_name not in api_configs:
            continue
        test_entries.append({
            "file": f,
            "api_name": api_name,
            "dt_str": dt_str,
            "ip": ip,
            "raw_data": f.read_text(encoding="utf-8"),
        })

    logger.info("Loaded %d raw test data entries", len(test_entries))

    # ── 5. Seed test maintenance ─────────────────────────────────
    from app.db.models import MaintenanceConfig, MaintenanceDeviceList

    test_mid = "TS-001"

    # Collect unique devices from test entries
    seen_devices: set[str] = set()
    device_rows = []
    for entry in test_entries:
        key = f"{entry['dt_str']}_{entry['ip']}"
        if key in seen_devices:
            continue
        seen_devices.add(key)
        hostname = f"SW-TEST-{entry['dt_str'].upper()}-{entry['ip'].replace('.', '-')}"
        vendor_map = {"hpe": "HPE", "ios": "Cisco-IOS", "nxos": "Cisco-NXOS"}
        device_rows.append((hostname, entry["ip"], vendor_map[entry["dt_str"]]))

    async with mem_session() as session:
        from datetime import datetime, timezone

        session.add(MaintenanceConfig(
            maintenance_id=test_mid,
            name="Timeseries Test",
            is_active=True,
            last_activated_at=datetime.now(timezone.utc),
        ))
        for hostname, ip, vendor in device_rows:
            session.add(MaintenanceDeviceList(
                maintenance_id=test_mid,
                old_hostname=hostname,
                old_ip_address=ip,
                old_vendor=vendor,
                new_hostname=hostname,
                new_ip_address=ip,
                new_vendor=vendor,
            ))

    logger.info("Seeded maintenance '%s' with %d devices", test_mid, len(device_rows))

    # ── 6. Run N collection cycles ──────────────────────────────
    from sqlalchemy import func, select

    from app.core.enums import DeviceType
    from app.db.models import CollectionBatch, LatestCollectionBatch
    from app.parsers import parser_registry as pr
    from app.repositories.typed_records import get_typed_repo

    print()
    print("=" * 72)
    print(f"  Timeseries Test: {args.cycles} cycles, {args.interval}s interval")
    print(f"  {len(test_entries)} raw files per cycle")
    if args.mutate > 0:
        print(f"  Mutation every {args.mutate} cycles")
    print("=" * 72)

    cycle_stats: list[dict] = []

    for cycle in range(1, args.cycles + 1):
        t0 = _time.monotonic()
        new_batches = 0
        skipped = 0
        errors = 0

        # Determine if this cycle should mutate data
        do_mutate = args.mutate > 0 and cycle % args.mutate == 0

        for entry in test_entries:
            api_name = entry["api_name"]
            dt_str = entry["dt_str"]
            ip = entry["ip"]
            raw_data = entry["raw_data"]

            # Inject mutation: append a comment line
            if do_mutate:
                raw_data = raw_data + f"\n! cycle {cycle} mutation"

            device_type = DeviceType(DEVICE_TYPE_MAP[dt_str])
            source = api_configs[api_name].get("source", "")
            parser_command = f"{api_name}_{dt_str}_{source.lower()}"
            hostname = f"SW-TEST-{dt_str.upper()}-{ip.replace('.', '-')}"

            # Get parser
            parser_obj = pr.get(command=parser_command, device_type=device_type)
            if parser_obj is None:
                errors += 1
                continue

            # Parse
            try:
                parsed_items = parser_obj.parse(raw_data)
            except Exception:
                errors += 1
                continue

            # Save (with hash comparison)
            async with mem_session() as session:
                typed_repo = get_typed_repo(api_name, session)
                batch = await typed_repo.save_batch(
                    switch_hostname=hostname,
                    raw_data=raw_data,
                    parsed_items=parsed_items,
                    maintenance_id=test_mid,
                )
                if batch is not None:
                    new_batches += 1
                else:
                    skipped += 1

        elapsed = _time.monotonic() - t0
        cycle_stats.append({
            "cycle": cycle,
            "new": new_batches,
            "skipped": skipped,
            "errors": errors,
            "elapsed": elapsed,
            "mutated": do_mutate,
        })

        # Query DB stats
        async with mem_session() as session:
            batch_count = (await session.execute(
                select(func.count()).select_from(CollectionBatch)
            )).scalar()
            latest_count = (await session.execute(
                select(func.count()).select_from(LatestCollectionBatch)
            )).scalar()

        total_collections = new_batches + skipped
        skip_pct = (skipped / total_collections * 100) if total_collections > 0 else 0

        mutate_tag = " [MUTATED]" if do_mutate else ""
        print(
            f"  Cycle {cycle:3d}: "
            f"+{new_batches:2d} new, {skipped:2d} skip ({skip_pct:4.0f}%), "
            f"{errors:2d} err | "
            f"DB: {batch_count:4d} batches, {latest_count:3d} latest | "
            f"{elapsed:.2f}s{mutate_tag}"
        )

        if cycle < args.cycles:
            await asyncio.sleep(args.interval)

    # ── 7. Print summary ─────────────────────────────────────────
    print()
    print("-" * 72)

    total_new = sum(s["new"] for s in cycle_stats)
    total_skipped = sum(s["skipped"] for s in cycle_stats)
    total_errors = sum(s["errors"] for s in cycle_stats)
    total_all = total_new + total_skipped

    naive_batches = total_all  # without hash dedup
    actual_batches = total_new

    print(f"  Total collections: {total_all}")
    print(f"  New batches:       {total_new}")
    print(f"  Skipped (same):    {total_skipped}")
    print(f"  Errors:            {total_errors}")
    print()
    if naive_batches > 0:
        reduction = (1 - actual_batches / naive_batches) * 100
        print(f"  Without hash:  {naive_batches} batches (every cycle stored)")
        print(f"  With hash:     {actual_batches} batches (only changes)")
        print(f"  Reduction:     {reduction:.1f}%")
    print()

    # ── 8. Test query performance ────────────────────────────────
    print("  Query Performance:")

    async with mem_session() as session:
        repo = get_typed_repo("get_fan", session)
        t0 = _time.monotonic()
        latest = await repo.get_latest_per_device(test_mid)
        dt = (_time.monotonic() - t0) * 1000
        print(f"    get_latest_per_device(get_fan): {len(latest)} rows, {dt:.1f}ms")

    async with mem_session() as session:
        repo = get_typed_repo("get_fan", session)
        t0 = _time.monotonic()
        info = await repo.get_latest_batch_info(test_mid)
        dt = (_time.monotonic() - t0) * 1000
        print(f"    get_latest_batch_info(get_fan): {len(info)} rows, {dt:.1f}ms")

    async with mem_session() as session:
        repo = get_typed_repo("get_fan", session)
        first_hostname = device_rows[0][0] if device_rows else "SW-TEST"
        t0 = _time.monotonic()
        history = await repo.get_change_history(test_mid, first_hostname)
        dt = (_time.monotonic() - t0) * 1000
        print(f"    get_change_history({first_hostname}):  {len(history)} changes, {dt:.1f}ms")

    async with mem_session() as session:
        repo = get_typed_repo("get_fan", session)
        t0 = _time.monotonic()
        summary = await repo.get_all_changes_summary(test_mid)
        dt = (_time.monotonic() - t0) * 1000
        print(f"    get_all_changes_summary:        {len(summary)} devices, {dt:.1f}ms")

    print()
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
