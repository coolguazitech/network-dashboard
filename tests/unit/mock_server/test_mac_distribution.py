"""
Tests for MAC table hash-based distribution logic.

Verifies that _assign_macs_to_ports() deterministically distributes
MACs across switches, and that format/port-name helpers work correctly.
"""
from __future__ import annotations

import pytest

from mock_server.generators.mac_table import (
    _assign_macs_to_ports,
    _format_mac,
    _port_name,
)


# ── _format_mac ──────────────────────────────────────────────────────

class TestFormatMac:
    """Test MAC formatting for different device types."""

    def test_hpe_format(self):
        """HPE: xxxx-xxxx-xxxx"""
        assert _format_mac("00:11:22:33:44:55", "hpe") == "0011-2233-4455"

    def test_ios_format(self):
        """IOS: xxxx.xxxx.xxxx"""
        assert _format_mac("00:11:22:33:44:55", "ios") == "0011.2233.4455"

    def test_nxos_format(self):
        """NXOS: xxxx.xxxx.xxxx (same as IOS)"""
        assert _format_mac("00:11:22:33:44:55", "nxos") == "0011.2233.4455"

    def test_dash_separated_input(self):
        """Input with dashes should be normalized."""
        assert _format_mac("00-11-22-33-44-55", "ios") == "0011.2233.4455"

    def test_dot_separated_input(self):
        """Input with dots should be normalized."""
        assert _format_mac("0011.2233.4455", "hpe") == "0011-2233-4455"

    def test_invalid_length_returns_as_is(self):
        """Invalid MAC length returns original."""
        assert _format_mac("001122", "ios") == "001122"

    def test_uppercase_input(self):
        """Uppercase input should be lowercased."""
        assert _format_mac("AA:BB:CC:DD:EE:FF", "ios") == "aabb.ccdd.eeff"


# ── _port_name ───────────────────────────────────────────────────────

class TestPortName:
    """Test port name generation for different device types."""

    def test_hpe_port(self):
        assert _port_name("hpe", 1) == "GE1/0/1"
        assert _port_name("hpe", 24) == "GE1/0/24"

    def test_ios_port(self):
        assert _port_name("ios", 1) == "Gi1/0/1"
        assert _port_name("ios", 12) == "Gi1/0/12"

    def test_nxos_port(self):
        assert _port_name("nxos", 1) == "Eth1/1"
        assert _port_name("nxos", 24) == "Eth1/24"


# ── _assign_macs_to_ports ───────────────────────────────────────────

class TestAssignMacsToPorts:
    """Test the hash-based MAC distribution logic."""

    SAMPLE_MACS = [
        {"mac_address": f"00:11:22:E0:01:{i:02X}"} for i in range(1, 21)
    ]

    def test_deterministic(self):
        """Same input always produces same output."""
        r1 = _assign_macs_to_ports("10.1.2.11", self.SAMPLE_MACS, "ios")
        r2 = _assign_macs_to_ports("10.1.2.11", self.SAMPLE_MACS, "ios")
        assert r1 == r2

    def test_different_switches_get_different_macs(self):
        """Different switch IPs produce different sets of MACs."""
        r1 = _assign_macs_to_ports("10.1.2.11", self.SAMPLE_MACS, "ios")
        r2 = _assign_macs_to_ports("10.1.2.12", self.SAMPLE_MACS, "ios")
        macs1 = {e["mac"] for e in r1}
        macs2 = {e["mac"] for e in r2}
        # They should overlap partially but not be identical
        assert macs1 != macs2

    def test_approximately_one_third(self):
        """Roughly 1/3 of MACs should land on each switch (with some variance)."""
        # Use larger sample for statistics
        big_macs = [{"mac_address": f"AA:BB:CC:DD:{i // 256:02X}:{i % 256:02X}"}
                     for i in range(300)]
        result = _assign_macs_to_ports("10.1.2.11", big_macs, "ios")
        ratio = len(result) / len(big_macs)
        # Should be roughly 1/3 (85/256 ≈ 0.332), allow 0.2-0.5 range
        assert 0.2 < ratio < 0.5, f"Ratio {ratio} outside expected range"

    def test_port_idx_range(self):
        """Port indices should be 1-24."""
        result = _assign_macs_to_ports("10.1.2.11", self.SAMPLE_MACS, "ios")
        for entry in result:
            # Port name is "Gi1/0/{idx}"
            idx = int(entry["port"].split("/")[-1])
            assert 1 <= idx <= 24, f"Port index {idx} out of range"

    def test_vlan_values(self):
        """VLANs should be from [10, 20, 100, 200]."""
        result = _assign_macs_to_ports("10.1.2.11", self.SAMPLE_MACS, "ios")
        valid_vlans = {10, 20, 100, 200}
        for entry in result:
            assert entry["vlan"] in valid_vlans

    def test_hpe_format_in_output(self):
        """HPE device type should produce GE port names and dash-format MACs."""
        result = _assign_macs_to_ports("10.1.2.21", self.SAMPLE_MACS, "hpe")
        assert len(result) > 0
        for entry in result:
            assert entry["port"].startswith("GE1/0/")
            assert "-" in entry["mac"]

    def test_nxos_format_in_output(self):
        """NXOS should produce Eth port names and dot-format MACs."""
        result = _assign_macs_to_ports("10.1.2.1", self.SAMPLE_MACS, "nxos")
        assert len(result) > 0
        for entry in result:
            assert entry["port"].startswith("Eth1/")
            assert "." in entry["mac"]

    def test_empty_mac_list_uses_fallback(self):
        """Empty MAC list should produce fallback entries."""
        result = _assign_macs_to_ports("10.1.2.11", [], "ios")
        assert len(result) == 5  # _generate_fallback_entries creates 5

    def test_no_valid_macs_uses_fallback(self):
        """If no MACs pass the hash filter, use fallback."""
        # Use a MAC list with just one MAC that might not land on this switch
        # We can't guarantee this, so use a MAC we know doesn't land
        # by checking hash: if all fail the filter, fallback is used
        result = _assign_macs_to_ports("10.1.2.11", [{"mac_address": ""}], "ios")
        assert len(result) == 5  # fallback

    def test_mac_without_address_key_skipped(self):
        """MAC entries without mac_address should be skipped."""
        macs = [{"not_a_mac": "value"}, {"mac_address": "00:11:22:33:44:55"}]
        result = _assign_macs_to_ports("10.1.2.11", macs, "ios")
        # At most 1 entry (the valid one, if it passes hash filter)
        assert len(result) <= 1 or len(result) == 5  # either it passed or fallback
