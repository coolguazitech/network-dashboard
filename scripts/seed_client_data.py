#!/usr/bin/env python3
"""
Seed Client Data for Network Dashboard.

Creates client_records (OLD + multiple rounds of NEW phase) and
client_comparisons for 100 MAC addresses defined in factory_device_config.

Final-round scenario distribution (deterministic, seed=42):
  - 70 no change   (severity: info)
  - 15 warning     (speed / duplex / VLAN change)
  - 10 critical    (link down / unreachable / port change)
  -  5 undetected  (no NEW record → critical)

Earlier rounds have more issues (progressive improvement over time):
  Round 1 (T-6h): +15 undetected, +5 warning, +3 critical
  Round 2 (T-3h): +5 undetected, +2 warning, +1 critical
  Round 3 (T-1h): final state (no extra issues)
"""
import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import delete

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import ClientComparison, ClientRecord
from app.services.client_comparison_service import ClientComparisonService

from factory_device_config import (
    MAINTENANCE_ID,
    generate_mac_addresses,
    get_device_mappings,
)

# Deterministic seed for reproducible results
SEED = 42

# Scenario counts (must sum to 100) — final round baseline
N_UNCHANGED = 70
N_WARNING = 15
N_CRITICAL = 10
N_UNDETECTED = 5

# Multi-round NEW collection configuration.
# Each round adds extra issues on top of the base scenarios.
# "extra_undetected" unchanged MACs become undetected for that round.
# "extra_warning" / "extra_critical" flip unchanged MACs to those severities.
# Rounds are ordered earliest → latest; nesting is enforced
# (Round 1's extras ⊇ Round 2's extras).
ROUNDS = [
    {"offset_hours": 6, "extra_undetected": 15, "extra_warning": 5, "extra_critical": 3},
    {"offset_hours": 3, "extra_undetected": 5, "extra_warning": 2, "extra_critical": 1},
    {"offset_hours": 1, "extra_undetected": 0, "extra_warning": 0, "extra_critical": 0},
]


def _get_category_switches() -> (
    dict[str, list[tuple[str, str, str, str]]]
):
    """
    Group device mappings by category.

    Returns:
        {category: [(old_h, old_ip, new_h, new_ip), ...]}
    """
    mappings = get_device_mappings()
    by_cat: dict[str, list[tuple[str, str, str, str]]] = {
        "EQP": [],
        "AMHS": [],
        "SNR": [],
        "OTHERS": [],
    }
    for old_h, old_ip, new_h, new_ip in mappings:
        dtype = old_h.split("-")[-1]
        if dtype in by_cat:
            by_cat[dtype].append((old_h, old_ip, new_h, new_ip))
    return by_cat


def _assign_scenarios(
    total: int,
    rng: random.Random,
) -> list[str]:
    """
    Assign scenario labels to MACs.

    Returns a shuffled list of scenario labels.
    """
    labels = (
        ["unchanged"] * N_UNCHANGED
        + ["warning"] * N_WARNING
        + ["critical"] * N_CRITICAL
        + ["undetected"] * N_UNDETECTED
    )
    assert len(labels) == total, (
        f"Scenario counts ({len(labels)}) != total MACs ({total})"
    )
    rng.shuffle(labels)
    return labels


def _compute_round_scenarios(
    base_scenarios: list[str],
    unchanged_indices: list[int],
    round_cfg: dict,
) -> list[str]:
    """
    Compute effective scenarios for a single round.

    Flips some 'unchanged' MACs to worse scenarios based on round_cfg.
    The unchanged_indices list is consumed from the front, so earlier
    rounds (called first with larger extras) use earlier indices,
    ensuring proper nesting (Round 1 extras ⊇ Round 2 extras).
    """
    result = list(base_scenarios)
    extra_u = round_cfg["extra_undetected"]
    extra_w = round_cfg["extra_warning"]
    extra_c = round_cfg["extra_critical"]
    total_extra = extra_u + extra_w + extra_c

    # Take the first N unchanged indices for this round's extras
    flip_indices = unchanged_indices[:total_extra]

    for i, idx in enumerate(flip_indices):
        if i < extra_u:
            result[idx] = "undetected"
        elif i < extra_u + extra_c:
            result[idx] = "critical"
        else:
            result[idx] = "warning"

    return result


def _build_old_record(
    mac: str,
    switch_hostname: str,
    switch_ip: str,
    port_idx: int,
    vlan_id: int,
    collected_at: datetime,
) -> ClientRecord:
    """Build a normal OLD-phase ClientRecord."""
    return ClientRecord(
        maintenance_id=MAINTENANCE_ID,
        phase=MaintenancePhase.OLD,
        collected_at=collected_at,
        mac_address=mac,
        ip_address=switch_ip,
        switch_hostname=switch_hostname,
        interface_name=f"GE1/0/{port_idx + 1}",
        vlan_id=vlan_id,
        speed="1G",
        duplex="full",
        link_status="up",
        ping_reachable=True,
        acl_passes=True,
    )


def _build_new_record_unchanged(
    mac: str,
    new_hostname: str,
    new_ip: str,
    port_idx: int,
    vlan_id: int,
    collected_at: datetime,
) -> ClientRecord:
    """Build a NEW-phase record with no changes (same port on new switch)."""
    return ClientRecord(
        maintenance_id=MAINTENANCE_ID,
        phase=MaintenancePhase.NEW,
        collected_at=collected_at,
        mac_address=mac,
        ip_address=new_ip,
        switch_hostname=new_hostname,
        interface_name=f"GE1/0/{port_idx + 1}",
        vlan_id=vlan_id,
        speed="1G",
        duplex="full",
        link_status="up",
        ping_reachable=True,
        acl_passes=True,
    )


def _build_new_record_warning(
    mac: str,
    new_hostname: str,
    new_ip: str,
    port_idx: int,
    vlan_id: int,
    collected_at: datetime,
    rng: random.Random,
) -> ClientRecord:
    """Build a NEW-phase record with warning-level changes."""
    change = rng.choice(["speed", "duplex", "vlan"])
    speed = "1G"
    duplex = "full"
    new_vlan = vlan_id

    if change == "speed":
        speed = "100M"
    elif change == "duplex":
        duplex = "half"
    else:
        new_vlan = vlan_id + 100

    return ClientRecord(
        maintenance_id=MAINTENANCE_ID,
        phase=MaintenancePhase.NEW,
        collected_at=collected_at,
        mac_address=mac,
        ip_address=new_ip,
        switch_hostname=new_hostname,
        interface_name=f"GE1/0/{port_idx + 1}",
        vlan_id=new_vlan,
        speed=speed,
        duplex=duplex,
        link_status="up",
        ping_reachable=True,
        acl_passes=True,
    )


def _build_new_record_critical(
    mac: str,
    new_hostname: str,
    new_ip: str,
    port_idx: int,
    vlan_id: int,
    collected_at: datetime,
    rng: random.Random,
) -> ClientRecord:
    """Build a NEW-phase record with critical-level changes."""
    change = rng.choice(["link_down", "unreachable", "port_change"])

    link_status = "up"
    ping_reachable = True
    interface = f"GE1/0/{port_idx + 1}"

    if change == "link_down":
        link_status = "down"
        ping_reachable = False
    elif change == "unreachable":
        ping_reachable = False
    else:
        # Port changed
        interface = f"GE1/0/{port_idx + 20}"

    return ClientRecord(
        maintenance_id=MAINTENANCE_ID,
        phase=MaintenancePhase.NEW,
        collected_at=collected_at,
        mac_address=mac,
        ip_address=new_ip,
        switch_hostname=new_hostname,
        interface_name=interface,
        vlan_id=vlan_id,
        speed="1G",
        duplex="full",
        link_status=link_status,
        ping_reachable=ping_reachable,
        acl_passes=True,
    )


async def main():
    """Seed client records and generate comparisons."""
    print("=" * 60)
    print("Seeding Client Data (Multi-Round)")
    print("=" * 60)

    rng = random.Random(SEED)

    # 1. Prepare data
    all_macs = generate_mac_addresses()
    cat_switches = _get_category_switches()
    base_scenarios = _assign_scenarios(100, rng)

    # Flatten MACs in category order
    flat_macs: list[tuple[str, str, str]] = []  # (mac, desc, category)
    for cat in ["EQP", "AMHS", "SNR", "OTHERS"]:
        for mac, desc in all_macs[cat]:
            flat_macs.append((mac, desc, cat))

    # Identify unchanged indices (deterministic order for nesting)
    unchanged_indices = [
        i for i, s in enumerate(base_scenarios) if s == "unchanged"
    ]
    rng.shuffle(unchanged_indices)

    # Timestamps
    now = datetime.utcnow()
    old_time = now - timedelta(days=7)

    # VLAN mapping by category
    vlan_map = {"EQP": 10, "AMHS": 20, "SNR": 30, "OTHERS": 40}

    # Pre-compute per-MAC switch info (shared across all rounds)
    mac_info: list[dict] = []
    for idx, (mac, desc, cat) in enumerate(flat_macs):
        switches = cat_switches[cat]
        sw_idx = idx % len(switches)
        old_h, old_ip, new_h, new_ip = switches[sw_idx]
        port_idx = idx // len(switches)
        vlan_id = vlan_map[cat]
        mac_info.append({
            "mac": mac, "cat": cat,
            "old_h": old_h, "old_ip": old_ip,
            "new_h": new_h, "new_ip": new_ip,
            "port_idx": port_idx, "vlan_id": vlan_id,
        })

    # 2. Clean + seed
    from app.db.base import init_db
    await init_db()

    async with get_session_context() as session:
        # Clean existing client data for TEST-100
        print("\nCleaning existing client data...")
        for tbl in [ClientComparison, ClientRecord]:
            stmt = delete(tbl).where(
                tbl.maintenance_id == MAINTENANCE_ID
            )
            result = await session.execute(stmt)
            print(
                f"  Deleted {result.rowcount} rows from "
                f"{tbl.__tablename__}"
            )
        await session.commit()

        # Build OLD records (single set, shared across all rounds)
        old_records: list[ClientRecord] = []
        for idx, info in enumerate(mac_info):
            old_rec = _build_old_record(
                info["mac"], info["old_h"], info["old_ip"],
                info["port_idx"], info["vlan_id"], old_time,
            )
            old_records.append(old_rec)

        print(f"\nSaving {len(old_records)} OLD-phase records...")
        for rec in old_records:
            session.add(rec)
        await session.flush()

        # Build NEW records for each round
        total_new = 0
        for round_idx, round_cfg in enumerate(ROUNDS):
            round_time = now - timedelta(hours=round_cfg["offset_hours"])
            round_scenarios = _compute_round_scenarios(
                base_scenarios, unchanged_indices, round_cfg,
            )

            # Use a per-round RNG so warning/critical variations
            # are consistent but independent per round
            round_rng = random.Random(SEED + round_idx + 1)

            new_records: list[ClientRecord] = []
            round_stats = {
                "unchanged": 0, "warning": 0,
                "critical": 0, "undetected": 0,
            }

            for idx, info in enumerate(mac_info):
                scenario = round_scenarios[idx]
                round_stats[scenario] += 1

                if scenario == "unchanged":
                    rec = _build_new_record_unchanged(
                        info["mac"], info["new_h"], info["new_ip"],
                        info["port_idx"], info["vlan_id"], round_time,
                    )
                    new_records.append(rec)
                elif scenario == "warning":
                    rec = _build_new_record_warning(
                        info["mac"], info["new_h"], info["new_ip"],
                        info["port_idx"], info["vlan_id"], round_time,
                        round_rng,
                    )
                    new_records.append(rec)
                elif scenario == "critical":
                    rec = _build_new_record_critical(
                        info["mac"], info["new_h"], info["new_ip"],
                        info["port_idx"], info["vlan_id"], round_time,
                        round_rng,
                    )
                    new_records.append(rec)
                # "undetected" → no NEW record

            print(
                f"\nRound {round_idx + 1} "
                f"(T-{round_cfg['offset_hours']}h): "
                f"{len(new_records)} NEW records"
            )
            for k, v in round_stats.items():
                print(f"  {k:12s} : {v}")

            for rec in new_records:
                session.add(rec)
            total_new += len(new_records)

        await session.commit()
        print(f"\nTotal NEW records saved: {total_new}")

        # 3. Generate comparisons (uses latest NEW per MAC)
        print("\nGenerating client comparisons...")
        svc = ClientComparisonService()
        comparisons = await svc.generate_comparisons(
            maintenance_id=MAINTENANCE_ID,
            session=session,
        )
        await svc.save_comparisons(comparisons, session)

        # 4. Summary
        sev_counts: dict[str, int] = {}
        for c in comparisons:
            sev = c.severity or "unknown"
            sev_counts[sev] = sev_counts.get(sev, 0) + 1

        print("\n" + "=" * 60)
        print("SEED SUMMARY")
        print("=" * 60)
        print(f"Maintenance ID : {MAINTENANCE_ID}")
        print(f"OLD records    : {len(old_records)}")
        print(f"NEW records    : {total_new} ({len(ROUNDS)} rounds)")
        print(f"Comparisons    : {len(comparisons)}")
        print(f"\nFinal severity distribution:")
        for k, v in sorted(sev_counts.items()):
            print(f"  {k:12s} : {v}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
