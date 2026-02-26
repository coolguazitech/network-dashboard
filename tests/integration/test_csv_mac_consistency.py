"""
Integration test: CSV data ↔ mock MAC table consistency.

Verifies that every client MAC in client_list.csv appears in at least
one switch's MAC table output (via the mock generator's hash logic),
and that the ghost device MAC is correctly handled.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from mock_server.generators.mac_table import _assign_macs_to_ports

TEST_DATA = Path(__file__).parent.parent.parent / "test_data"


def _load_csv(filename: str) -> list[dict]:
    with open(TEST_DATA / filename, encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def devices() -> list[dict]:
    return _load_csv("device_list.csv")


@pytest.fixture(scope="module")
def clients() -> list[dict]:
    return _load_csv("client_list.csv")


@pytest.fixture(scope="module")
def mac_list(clients: list[dict]) -> list[dict]:
    """MAC list in the format expected by the mock generator."""
    return [
        {"mac_address": c["mac_address"], "ip_address": c.get("ip_address", "")}
        for c in clients
    ]


def _vendor_to_device_type(vendor: str) -> str:
    """Convert vendor string to device_type for generator."""
    v = vendor.lower()
    if "nxos" in v or "nexus" in v:
        return "nxos"
    elif "hpe" in v:
        return "hpe"
    else:
        return "ios"


class TestCsvMacConsistency:
    """Ensure client MACs consistently appear in mock MAC table output."""

    def test_every_client_mac_found_on_at_least_one_new_switch(
        self, devices: list[dict], clients: list[dict], mac_list: list[dict],
    ):
        """
        Every client MAC (except ghost) should appear in at least one
        NEW switch's MAC table.
        """
        import random
        random.seed(0)  # 固定 seed 避免 NOT_DETECTED_PROB 隨機丟失

        ghost_mac = "00:11:22:99:99:99"

        # Collect all MACs found across all new switches
        found_macs: set[str] = set()

        for device in devices:
            new_ip = device.get("new_ip_address", "")
            new_vendor = device.get("new_vendor", "")
            if not new_ip or not new_vendor:
                continue

            device_type = _vendor_to_device_type(new_vendor)
            entries = _assign_macs_to_ports(new_ip, mac_list, device_type)

            for entry in entries:
                # Convert back from formatted MAC to colon-separated
                clean = entry["mac"].replace(".", "").replace("-", "")
                colon_mac = ":".join(
                    clean[i:i+2] for i in range(0, 12, 2)
                ).upper()
                found_macs.add(colon_mac)

        # Verify every non-ghost client MAC was found
        for client in clients:
            mac = client["mac_address"].upper()
            if mac == ghost_mac.upper():
                continue
            assert mac in found_macs, (
                f"Client MAC {mac} not found on any NEW switch's MAC table"
            )

    def test_every_client_mac_found_on_at_least_one_old_switch(
        self, devices: list[dict], clients: list[dict], mac_list: list[dict],
    ):
        """
        Every client MAC (except ghost) should appear in at least one
        OLD switch's MAC table.
        """
        import random
        random.seed(0)  # 固定 seed 避免 NOT_DETECTED_PROB 隨機丟失

        ghost_mac = "00:11:22:99:99:99"

        found_macs: set[str] = set()

        for device in devices:
            old_ip = device.get("old_ip_address", "")
            old_vendor = device.get("old_vendor", "")
            if not old_ip or not old_vendor:
                continue

            device_type = _vendor_to_device_type(old_vendor)
            entries = _assign_macs_to_ports(old_ip, mac_list, device_type)

            for entry in entries:
                clean = entry["mac"].replace(".", "").replace("-", "")
                colon_mac = ":".join(
                    clean[i:i+2] for i in range(0, 12, 2)
                ).upper()
                found_macs.add(colon_mac)

        for client in clients:
            mac = client["mac_address"].upper()
            if mac == ghost_mac.upper():
                continue
            assert mac in found_macs, (
                f"Client MAC {mac} not found on any OLD switch's MAC table"
            )

    def test_ghost_device_is_found_but_marked_unreachable(
        self, clients: list[dict],
    ):
        """
        Ghost device MAC should still land on some switches (hash doesn't
        care about the 'ghost' label), but mock_network_state.csv marks
        it as ping_reachable=false.
        """
        ghost_mac = "00:11:22:99:99:99"
        ghost = [c for c in clients if c["mac_address"] == ghost_mac]
        assert len(ghost) == 1, "Expected exactly one ghost device"

        # Verify in mock_network_state.csv that ghost entries are unreachable
        network_state = _load_csv("mock_network_state.csv")
        ghost_rows = [
            r for r in network_state
            if r["mac_address"] == ghost_mac
        ]
        assert len(ghost_rows) > 0, "Ghost MAC should appear in network state"
        for row in ghost_rows:
            assert row["ping_reachable"] == "false", (
                f"Ghost MAC should be unreachable, but got {row['ping_reachable']}"
            )

    def test_mock_network_state_matches_hash_distribution(
        self, devices: list[dict], mac_list: list[dict],
    ):
        """
        mock_network_state.csv entries should match the hash-based
        distribution from the generator.
        """
        from unittest.mock import patch

        # 停用隨機性：此測試驗證確定性 hash 分配邏輯，不應受 per-MAC 隨機影響
        with patch("mock_server.generators.mac_table.NOT_DETECTED_PROB", 0), \
             patch("mock_server.generators.mac_table.VLAN_CHANGE_PROB", 0), \
             patch("mock_server.generators.mac_table.PORT_CHANGE_PROB", 0):
            self._verify_hash_distribution(devices)

    def _verify_hash_distribution(self, devices: list[dict]) -> None:
        network_state = _load_csv("mock_network_state.csv")

        # Build expected: for each (mac, switch_hostname) pair, verify it
        # matches the hash logic
        device_by_hostname: dict[str, dict] = {}
        for device in devices:
            for phase, host_key, ip_key, vendor_key in [
                ("old", "old_hostname", "old_ip_address", "old_vendor"),
                ("new", "new_hostname", "new_ip_address", "new_vendor"),
            ]:
                hostname = device.get(host_key, "")
                if hostname:
                    device_by_hostname[hostname] = {
                        "ip": device.get(ip_key, ""),
                        "vendor": device.get(vendor_key, ""),
                    }

        # Sample check: pick first 50 rows from network_state
        for row in network_state[:50]:
            mac = row["mac_address"]
            hostname = row["switch_hostname"]

            device_info = device_by_hostname.get(hostname)
            if device_info is None:
                continue  # Could be a switch not in device_list

            switch_ip = device_info["ip"]
            device_type = _vendor_to_device_type(device_info["vendor"])

            # Run the hash to verify this MAC should land on this switch
            entries = _assign_macs_to_ports(
                switch_ip,
                [{"mac_address": mac}],
                device_type,
            )
            # entries has either 0 (falls back) or 1 entry
            # If 0, the MAC went to fallback — not our MAC
            found = any(
                e for e in entries
                if mac.replace(":", "").lower() in
                e["mac"].replace(".", "").replace("-", "")
            )
            assert found, (
                f"mock_network_state says {mac} is on {hostname} "
                f"(IP={switch_ip}), but hash disagrees"
            )

    def test_total_client_count_matches(
        self, clients: list[dict],
    ):
        """Client list should have expected number of entries."""
        assert len(clients) >= 15, (
            f"Expected at least 15 clients, got {len(clients)}"
        )

    def test_device_types_present(self, devices: list[dict]):
        """Should have NXOS, IOS, and HPE devices."""
        vendors = {d.get("new_vendor", "").lower() for d in devices}
        has_nxos = any("nxos" in v for v in vendors)
        has_ios = any("ios" in v for v in vendors)
        has_hpe = any("hpe" in v for v in vendors)
        assert has_nxos, "Expected NXOS devices"
        assert has_ios, "Expected IOS devices"
        assert has_hpe, "Expected HPE devices"
