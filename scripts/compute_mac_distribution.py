#!/usr/bin/env python3
"""
Compute MAC->switch distribution using the same hash logic as
mock_server/generators/mac_table.py:_assign_macs_to_ports().

Used to:
1. Verify which MACs land on which switches.
2. Generate consistent mock_network_state.csv.
3. Find MACs that don't land on ANY switch (need adjustment).

Usage:
    python scripts/compute_mac_distribution.py            # display distribution
    python scripts/compute_mac_distribution.py --generate  # regenerate CSV
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

TEST_DATA = Path(__file__).parent.parent / "test_data"


def mac_lands_on_switch(mac: str, switch_ip: str) -> dict | None:
    """
    Replicate the hash logic from mac_table.py:_assign_macs_to_ports().

    Returns port assignment dict if MAC lands on this switch, else None.
    """
    h = hashlib.md5(f"{mac}:{switch_ip}".encode()).hexdigest()
    # ~1/3 probability: int(h[:2], 16) < 85
    if int(h[:2], 16) >= 85:
        return None

    port_idx = int(h[2:4], 16) % 24 + 1
    vlan_id = [10, 20, 100, 200][int(h[4:6], 16) % 4]

    return {"port_idx": port_idx, "vlan_id": vlan_id}


def port_name(vendor: str, port_idx: int) -> str:
    """Generate port name matching mock_server/generators convention."""
    v = vendor.lower()
    if "hpe" in v:
        return f"GE1/0/{port_idx}"
    elif "nxos" in v or "nexus" in v:
        return f"Eth1/{port_idx}"
    else:  # ios
        return f"Gi1/0/{port_idx}"


def load_devices() -> list[dict]:
    with open(TEST_DATA / "device_list.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_clients() -> list[dict]:
    with open(TEST_DATA / "client_list.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_distribution(
    devices: list[dict],
    clients: list[dict],
) -> list[dict]:
    """
    For each client MAC, find which switches it lands on (for both OLD and NEW).

    Returns list of rows for mock_network_state.csv.
    """
    rows: list[dict] = []
    client_ip_map = {c["mac_address"]: c.get("ip_address", "") for c in clients}
    ghost_mac = "00:11:22:99:99:99"

    for client in clients:
        mac = client["mac_address"]
        ip = client.get("ip_address", "")
        is_ghost = mac == ghost_mac

        for device in devices:
            for phase, ip_key, host_key, vendor_key in [
                ("old", "old_ip_address", "old_hostname", "old_vendor"),
                ("new", "new_ip_address", "new_hostname", "new_vendor"),
            ]:
                switch_ip = device.get(ip_key, "")
                hostname = device.get(host_key, "")
                vendor = device.get(vendor_key, "")
                if not switch_ip or not hostname:
                    continue

                assignment = mac_lands_on_switch(mac, switch_ip)
                if assignment is None:
                    continue

                iface = port_name(vendor, assignment["port_idx"])
                ping = "false" if is_ghost else "true"

                rows.append({
                    "mac_address": mac,
                    "ip_address": ip,
                    "switch_hostname": hostname,
                    "interface": iface,
                    "vlan": assignment["vlan_id"],
                    "ping_reachable": ping,
                })

    return rows


def generate_csv(rows: list[dict]) -> None:
    """Write mock_network_state.csv."""
    out = TEST_DATA / "mock_network_state.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["mac_address", "ip_address", "switch_hostname",
                         "interface", "vlan", "ping_reachable"],
        )
        writer.writeheader()
        # Sort for deterministic output
        rows.sort(key=lambda r: (r["mac_address"], r["switch_hostname"]))
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")


def display(devices: list[dict], clients: list[dict], rows: list[dict]) -> int:
    """Display distribution summary."""
    print(f"Devices: {len(devices)}, Clients: {len(clients)}")
    print("=" * 80)

    # Group by MAC
    by_mac: dict[str, list[dict]] = {}
    for row in rows:
        by_mac.setdefault(row["mac_address"], []).append(row)

    orphan_macs = []
    for mac in sorted(set(c["mac_address"] for c in clients)):
        hits = by_mac.get(mac, [])
        if not hits:
            orphan_macs.append(mac)
            print(f"  {mac}: *** NO SWITCH (orphan) ***")
        else:
            old = [h for h in hits if h["switch_hostname"].startswith("SW-OLD")]
            new = [h for h in hits if h["switch_hostname"].startswith("SW-NEW")]
            print(f"  {mac}: OLD={len(old)} switches, NEW={len(new)} switches")

    print("=" * 80)
    print(f"Total rows: {len(rows)}")
    print(f"Orphan MACs: {len(orphan_macs)}")
    return 0 if not orphan_macs else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true",
                        help="Regenerate mock_network_state.csv")
    args = parser.parse_args()

    devices = load_devices()
    clients = load_clients()
    rows = compute_distribution(devices, clients)

    if args.generate:
        generate_csv(rows)
        return 0

    return display(devices, clients, rows)


if __name__ == "__main__":
    sys.exit(main())
