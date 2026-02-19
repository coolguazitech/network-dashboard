#!/usr/bin/env python3
"""
End-to-end pipeline verification script.

Uses SQLite in-memory DB + raw test data files to verify the parser → DB pipeline:
    test_data/raw/*.txt → parser → typed_records → DB

Usage:
    python scripts/verify_pipeline.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("verify")

# Raw test data directory
RAW_DIR = Path("test_data/raw")

# Device type mapping: filename token → DeviceType enum value
DEVICE_TYPE_MAP = {
    "hpe": "HPE",
    "ios": "Cisco-IOS",
    "nxos": "Cisco-NXOS",
}


async def main() -> None:
    # ── 1. Override DB to SQLite in-memory ──────────────────────
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite in-memory DB created (%d tables)", len(Base.metadata.tables))

    # Context manager that yields an in-memory session
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mem_session():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ── 2. Discover parsers ─────────────────────────────────────
    from app.parsers.registry import auto_discover_parsers, parser_registry

    parser_registry.clear()
    count = auto_discover_parsers()
    logger.info("Discovered %d parser modules, %d parsers registered", count, len(parser_registry.list_parsers()))

    # ── 3. Load scheduler.yaml to get source mapping ─────────────
    import yaml

    with open("config/scheduler.yaml") as f:
        cfg = yaml.safe_load(f)

    api_configs = cfg.get("fetchers", {})
    logger.info("scheduler.yaml defines %d APIs", len(api_configs))

    # ── 4. Seed a test maintenance ───────────────────────────────
    from app.db.models import MaintenanceConfig, MaintenanceDeviceList

    test_mid = "TEST-001"

    async with mem_session() as session:
        session.add(MaintenanceConfig(
            maintenance_id=test_mid,
            name="Test Maintenance",
            is_active=True,
        ))
        session.add(MaintenanceDeviceList(
            maintenance_id=test_mid,
            old_hostname="SW-TEST-HPE-01",
            old_ip_address="10.10.1.1",
            old_vendor="HPE",
            new_hostname="SW-TEST-HPE-01",
            new_ip_address="10.10.1.1",
            new_vendor="HPE",
        ))

    logger.info("Seeded maintenance '%s'", test_mid)

    # ── 5. Find raw test data files and run parser → DB ──────────
    from app.core.enums import DeviceType
    from app.parsers import parser_registry as pr
    from app.repositories.typed_records import get_typed_repo

    results: list[dict] = []

    if not RAW_DIR.exists():
        logger.error("Raw test data directory not found: %s", RAW_DIR)
        sys.exit(1)

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    logger.info("Found %d raw test data files", len(raw_files))

    for raw_file in raw_files:
        # Parse filename: {api_name}_{device_type}_{ip}.txt
        parts = raw_file.stem.split("_")
        # api_name is variable length (e.g. get_gbic_details, get_fan)
        # device_type is one of hpe/ios/nxos
        # ip is like 10.10.1.1

        # Find device_type token position
        dt_idx = None
        for i, part in enumerate(parts):
            if part in DEVICE_TYPE_MAP:
                dt_idx = i
                break

        if dt_idx is None:
            results.append({"file": raw_file.name, "status": "SKIP", "error": "no device_type in filename"})
            continue

        api_name = "_".join(parts[:dt_idx])
        dt_str = parts[dt_idx]
        device_type = DeviceType(DEVICE_TYPE_MAP[dt_str])

        # Check if API exists in scheduler config
        if api_name not in api_configs:
            results.append({"file": raw_file.name, "status": "SKIP", "error": f"API '{api_name}' not in scheduler.yaml"})
            continue

        source = api_configs[api_name].get("source", "")
        parser_command = f"{api_name}_{dt_str}_{source.lower()}"

        # Get parser
        parser = pr.get(command=parser_command, device_type=device_type)
        if parser is None:
            results.append({"file": raw_file.name, "status": "NO_PARSER", "command": parser_command})
            continue

        # Read raw data
        raw_output = raw_file.read_text(encoding="utf-8")
        raw_len = len(raw_output)

        # Parse
        try:
            parsed_items = parser.parse(raw_output)
        except Exception as e:
            results.append({"file": raw_file.name, "status": "PARSE_ERROR", "error": str(e)})
            continue

        # Save to DB
        try:
            async with mem_session() as session:
                typed_repo = get_typed_repo(api_name, session)
                await typed_repo.save_batch(
                    switch_hostname=f"SW-TEST-{dt_str.upper()}-01",
                    raw_data=raw_output,
                    parsed_items=parsed_items,
                    maintenance_id=test_mid,
                )
        except Exception as e:
            results.append({
                "file": raw_file.name,
                "status": "DB_ERROR",
                "parsed": len(parsed_items),
                "error": str(e),
            })
            continue

        results.append({
            "file": raw_file.name,
            "status": "OK",
            "raw_chars": raw_len,
            "parsed": len(parsed_items),
            "parser": parser_command,
        })

    # ── 6. Print summary ────────────────────────────────────────
    print()
    print("=" * 72)
    print("Pipeline Verification Results")
    print("=" * 72)

    ok_count = 0
    fail_count = 0
    skip_count = 0

    for r in results:
        fname = r["file"]
        status = r["status"]

        if status == "OK":
            ok_count += 1
            print(f"  OK   {fname:<45} → {r['parsed']:>3} items  ({r['parser']})")
        elif status == "SKIP":
            skip_count += 1
        else:
            fail_count += 1
            detail = r.get("error") or r.get("command") or ""
            print(f"  FAIL {fname:<45} → {status}: {detail}")

    print("-" * 72)
    print(f"  {ok_count} OK, {fail_count} FAIL, {skip_count} SKIP (total {len(results)})")
    print("=" * 72)

    # ── 7. Verify DB contents ───────────────────────────────────
    from sqlalchemy import select, func
    from app.db.models import CollectionBatch

    async with mem_session() as session:
        batch_count = (await session.execute(
            select(func.count()).select_from(CollectionBatch)
        )).scalar()
        print(f"\n  CollectionBatch rows in DB: {batch_count}")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
