"""Tests for ClientComparisonService helper methods.

Covers the pure synchronous helpers:
- _normalize_speed()
- _normalize_duplex()
- _normalize_link_status()
- _find_differences()
- _has_any_data()
"""
from __future__ import annotations

import pytest

from app.db.models import ClientComparison
from app.services.client_comparison_service import ClientComparisonService


# ---------------------------------------------------------------------------
# Fixture: shared service instance
# ---------------------------------------------------------------------------

@pytest.fixture
def service() -> ClientComparisonService:
    """Create a fresh ClientComparisonService for each test."""
    return ClientComparisonService()


def _make_comparison(**kwargs) -> ClientComparison:
    """Build a ClientComparison with sensible defaults and optional overrides.

    All old_*/new_* fields default to ``None`` so individual tests only
    need to set the fields they care about.
    """
    defaults = {
        "maintenance_id": "M-TEST",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        # old side
        "old_ip_address": None,
        "old_switch_hostname": None,
        "old_interface_name": None,
        "old_vlan_id": None,
        "old_speed": None,
        "old_duplex": None,
        "old_link_status": None,
        "old_ping_reachable": None,
        # new side
        "new_ip_address": None,
        "new_switch_hostname": None,
        "new_interface_name": None,
        "new_vlan_id": None,
        "new_speed": None,
        "new_duplex": None,
        "new_link_status": None,
        "new_ping_reachable": None,
    }
    defaults.update(kwargs)
    return ClientComparison(**defaults)


# ===================================================================
# _normalize_speed
# ===================================================================

class TestNormalizeSpeed:
    """_normalize_speed(speed) -> int | None"""

    def test_normalize_speed_1000mbps(self, service: ClientComparisonService):
        # "1000M" should parse to 1000
        assert service._normalize_speed("1000M") == 1000

    def test_normalize_speed_auto(self, service: ClientComparisonService):
        # "auto" maps to the sentinel value -1
        assert service._normalize_speed("auto") == -1

    def test_normalize_speed_10g(self, service: ClientComparisonService):
        # "10G" -> 10 * 1000 = 10000
        assert service._normalize_speed("10G") == 10000

    def test_normalize_speed_1g(self, service: ClientComparisonService):
        # "1G" -> 1000
        assert service._normalize_speed("1G") == 1000

    def test_normalize_speed_100m(self, service: ClientComparisonService):
        # "100M" -> 100
        assert service._normalize_speed("100M") == 100

    def test_normalize_speed_none(self, service: ClientComparisonService):
        assert service._normalize_speed(None) is None

    def test_normalize_speed_empty_string(self, service: ClientComparisonService):
        assert service._normalize_speed("") is None

    def test_normalize_speed_whitespace(self, service: ClientComparisonService):
        assert service._normalize_speed("  ") is None

    def test_normalize_speed_unknown_string(self, service: ClientComparisonService):
        # A string that does not match any pattern returns None
        assert service._normalize_speed("unknown") is None

    def test_normalize_speed_pure_number_string(self, service: ClientComparisonService):
        # A bare number string is treated as Mbps
        assert service._normalize_speed("100") == 100

    def test_normalize_speed_case_insensitive(self, service: ClientComparisonService):
        # "10g" (lowercase) should still parse to 10000
        assert service._normalize_speed("10g") == 10000

    def test_normalize_speed_auto_uppercase(self, service: ClientComparisonService):
        assert service._normalize_speed("AUTO") == -1

    def test_normalize_speed_auto_mixed_case(self, service: ClientComparisonService):
        assert service._normalize_speed("Auto") == -1

    def test_normalize_speed_25g(self, service: ClientComparisonService):
        assert service._normalize_speed("25G") == 25000

    def test_normalize_speed_40g(self, service: ClientComparisonService):
        assert service._normalize_speed("40G") == 40000

    def test_normalize_speed_100g(self, service: ClientComparisonService):
        assert service._normalize_speed("100G") == 100000

    def test_normalize_speed_10m(self, service: ClientComparisonService):
        assert service._normalize_speed("10M") == 10


# ===================================================================
# _normalize_duplex
# ===================================================================

class TestNormalizeDuplex:
    """_normalize_duplex(duplex) -> str | None"""

    def test_normalize_duplex_full(self, service: ClientComparisonService):
        assert service._normalize_duplex("full") == "full"

    def test_normalize_duplex_capitalized(self, service: ClientComparisonService):
        assert service._normalize_duplex("Full") == "full"

    def test_normalize_duplex_uppercase(self, service: ClientComparisonService):
        assert service._normalize_duplex("FULL") == "full"

    def test_normalize_duplex_a_full(self, service: ClientComparisonService):
        # "a-full" lowered is "a-full", not "full". The method only strips
        # whitespace and lowercases -- it does NOT extract the suffix.
        assert service._normalize_duplex("a-full") == "a-full"

    def test_normalize_duplex_half(self, service: ClientComparisonService):
        assert service._normalize_duplex("half") == "half"

    def test_normalize_duplex_half_capitalized(self, service: ClientComparisonService):
        assert service._normalize_duplex("Half") == "half"

    def test_normalize_duplex_none(self, service: ClientComparisonService):
        assert service._normalize_duplex(None) is None

    def test_normalize_duplex_auto(self, service: ClientComparisonService):
        # "auto" is simply lowered; no special handling
        assert service._normalize_duplex("auto") == "auto"

    def test_normalize_duplex_auto_uppercase(self, service: ClientComparisonService):
        assert service._normalize_duplex("AUTO") == "auto"

    def test_normalize_duplex_empty_string(self, service: ClientComparisonService):
        # Empty string after strip → falsy → returns None (via ``or None``)
        assert service._normalize_duplex("") is None

    def test_normalize_duplex_whitespace_only(self, service: ClientComparisonService):
        # Whitespace-only string strips to empty → returns None
        assert service._normalize_duplex("   ") is None

    def test_normalize_duplex_with_whitespace(self, service: ClientComparisonService):
        assert service._normalize_duplex("  Full  ") == "full"


# ===================================================================
# _normalize_link_status
# ===================================================================

class TestNormalizeLinkStatus:
    """_normalize_link_status(status) -> str | None

    This method only strips whitespace and lowercases.  It does NOT
    remap Cisco IOS terms like 'connected' -> 'up'.
    """

    def test_normalize_link_connected(self, service: ClientComparisonService):
        # 'connected' is lowered as-is (no remapping)
        assert service._normalize_link_status("connected") == "connected"

    def test_normalize_link_up(self, service: ClientComparisonService):
        assert service._normalize_link_status("up") == "up"

    def test_normalize_link_up_uppercase(self, service: ClientComparisonService):
        assert service._normalize_link_status("UP") == "up"

    def test_normalize_link_notconnect(self, service: ClientComparisonService):
        # Not remapped, just lowered
        assert service._normalize_link_status("notconnect") == "notconnect"

    def test_normalize_link_down(self, service: ClientComparisonService):
        assert service._normalize_link_status("down") == "down"

    def test_normalize_link_down_uppercase(self, service: ClientComparisonService):
        assert service._normalize_link_status("DOWN") == "down"

    def test_normalize_link_none(self, service: ClientComparisonService):
        assert service._normalize_link_status(None) is None

    def test_normalize_link_empty_string(self, service: ClientComparisonService):
        assert service._normalize_link_status("") is None

    def test_normalize_link_whitespace(self, service: ClientComparisonService):
        assert service._normalize_link_status("  ") is None

    def test_normalize_link_with_whitespace(self, service: ClientComparisonService):
        assert service._normalize_link_status("  Up  ") == "up"


# ===================================================================
# _find_differences
# ===================================================================

class TestFindDifferences:
    """_find_differences(comparison) -> dict[str, Any]"""

    def test_find_differences_no_changes(self, service: ClientComparisonService):
        """Same old/new values produce no differences."""
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            new_switch_hostname="SW-01",
            old_interface_name="GE1/0/1",
            new_interface_name="GE1/0/1",
            old_vlan_id=10,
            new_vlan_id=10,
            old_speed="1G",
            new_speed="1G",
            old_duplex="full",
            new_duplex="full",
            old_link_status="up",
            new_link_status="up",
            old_ip_address="10.0.0.1",
            new_ip_address="10.0.0.1",
            old_ping_reachable=True,
            new_ping_reachable=True,
        )
        diffs = service._find_differences(comp)
        assert diffs == {}

    def test_find_differences_switch_changed(self, service: ClientComparisonService):
        """Different switch_hostname is detected as a difference."""
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            new_switch_hostname="SW-02",
            old_interface_name="GE1/0/1",
            new_interface_name="GE1/0/1",
        )
        diffs = service._find_differences(comp)
        assert "switch_hostname" in diffs
        assert diffs["switch_hostname"]["old"] == "SW-01"
        assert diffs["switch_hostname"]["new"] == "SW-02"

    def test_find_differences_speed_changed(self, service: ClientComparisonService):
        """Different speed is listed as a difference."""
        comp = _make_comparison(
            old_speed="100M",
            new_speed="1G",
        )
        diffs = service._find_differences(comp)
        assert "speed" in diffs
        assert diffs["speed"]["old"] == "100M"
        assert diffs["speed"]["new"] == "1G"

    def test_find_differences_speed_equivalent_no_diff(
        self, service: ClientComparisonService
    ):
        """1G and 1000M normalize to the same value -- no difference."""
        comp = _make_comparison(
            old_speed="1G",
            new_speed="1000M",
        )
        diffs = service._find_differences(comp)
        assert "speed" not in diffs

    def test_find_differences_duplex_case_no_diff(
        self, service: ClientComparisonService
    ):
        """'Full' and 'full' normalize identically -- no difference."""
        comp = _make_comparison(
            old_duplex="Full",
            new_duplex="full",
        )
        diffs = service._find_differences(comp)
        assert "duplex" not in diffs

    def test_find_differences_duplex_changed(self, service: ClientComparisonService):
        comp = _make_comparison(
            old_duplex="full",
            new_duplex="half",
        )
        diffs = service._find_differences(comp)
        assert "duplex" in diffs
        assert diffs["duplex"]["old"] == "full"
        assert diffs["duplex"]["new"] == "half"

    def test_find_differences_link_status_case_no_diff(
        self, service: ClientComparisonService
    ):
        """'UP' and 'up' normalize identically -- no difference."""
        comp = _make_comparison(
            old_link_status="UP",
            new_link_status="up",
        )
        diffs = service._find_differences(comp)
        assert "link_status" not in diffs

    def test_find_differences_link_status_changed(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(
            old_link_status="up",
            new_link_status="down",
        )
        diffs = service._find_differences(comp)
        assert "link_status" in diffs

    def test_find_differences_multiple_changes(self, service: ClientComparisonService):
        """Multiple fields changed are all reported."""
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            new_switch_hostname="SW-02",
            old_interface_name="GE1/0/1",
            new_interface_name="GE1/0/2",
            old_vlan_id=10,
            new_vlan_id=20,
            old_speed="100M",
            new_speed="1G",
        )
        diffs = service._find_differences(comp)
        assert "switch_hostname" in diffs
        assert "interface_name" in diffs
        assert "vlan_id" in diffs
        assert "speed" in diffs

    def test_find_differences_one_side_none_ignored(
        self, service: ClientComparisonService
    ):
        """When one side is None, the field is NOT reported as changed
        (for non-speed/duplex/link_status fields, both must be non-None).
        """
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            new_switch_hostname=None,
        )
        diffs = service._find_differences(comp)
        assert "switch_hostname" not in diffs

    def test_find_differences_speed_one_side_none_skipped(
        self, service: ClientComparisonService
    ):
        """Speed comparison skipped when one side normalizes to None."""
        comp = _make_comparison(
            old_speed="1G",
            new_speed=None,
        )
        diffs = service._find_differences(comp)
        assert "speed" not in diffs

    def test_find_differences_duplex_one_side_none_skipped(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(
            old_duplex="full",
            new_duplex=None,
        )
        diffs = service._find_differences(comp)
        assert "duplex" not in diffs

    def test_find_differences_link_status_one_side_none_skipped(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(
            old_link_status="up",
            new_link_status=None,
        )
        diffs = service._find_differences(comp)
        assert "link_status" not in diffs

    def test_find_differences_ping_reachable_changed(
        self, service: ClientComparisonService
    ):
        """Boolean ping_reachable difference is detected when both non-None."""
        comp = _make_comparison(
            old_ping_reachable=True,
            new_ping_reachable=False,
        )
        diffs = service._find_differences(comp)
        assert "ping_reachable" in diffs
        assert diffs["ping_reachable"]["old"] is True
        assert diffs["ping_reachable"]["new"] is False

    def test_find_differences_ping_reachable_one_none_skipped(
        self, service: ClientComparisonService
    ):
        """ping_reachable requires both sides non-None to compare."""
        comp = _make_comparison(
            old_ping_reachable=True,
            new_ping_reachable=None,
        )
        diffs = service._find_differences(comp)
        assert "ping_reachable" not in diffs

    def test_find_differences_ip_address_changed(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(
            old_ip_address="10.0.0.1",
            new_ip_address="10.0.0.2",
        )
        diffs = service._find_differences(comp)
        assert "ip_address" in diffs
        assert diffs["ip_address"]["old"] == "10.0.0.1"
        assert diffs["ip_address"]["new"] == "10.0.0.2"


# ===================================================================
# _has_any_data
# ===================================================================

class TestHasAnyData:
    """_has_any_data(comparison, prefix) -> bool"""

    def test_has_any_data_with_old_ip(self, service: ClientComparisonService):
        comp = _make_comparison(old_ip_address="10.0.0.1")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_switch_hostname(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(old_switch_hostname="SW-01")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_interface(self, service: ClientComparisonService):
        comp = _make_comparison(old_interface_name="GE1/0/1")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_vlan(self, service: ClientComparisonService):
        comp = _make_comparison(old_vlan_id=10)
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_speed(self, service: ClientComparisonService):
        comp = _make_comparison(old_speed="1G")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_duplex(self, service: ClientComparisonService):
        comp = _make_comparison(old_duplex="full")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_with_old_link_status(
        self, service: ClientComparisonService
    ):
        comp = _make_comparison(old_link_status="up")
        assert service._has_any_data(comp, "old") is True

    def test_has_any_data_all_old_none(self, service: ClientComparisonService):
        """All old_* fields are None -> False."""
        comp = _make_comparison()
        assert service._has_any_data(comp, "old") is False

    def test_has_any_data_all_new_none(self, service: ClientComparisonService):
        """All new_* fields are None -> False."""
        comp = _make_comparison()
        assert service._has_any_data(comp, "new") is False

    def test_has_any_data_new_with_values(self, service: ClientComparisonService):
        comp = _make_comparison(new_switch_hostname="SW-02")
        assert service._has_any_data(comp, "new") is True

    def test_has_any_data_empty_string_treated_as_no_data(
        self, service: ClientComparisonService
    ):
        """Empty string is explicitly excluded (value != '')."""
        comp = _make_comparison(old_switch_hostname="")
        assert service._has_any_data(comp, "old") is False

    def test_has_any_data_does_not_check_ping_reachable(
        self, service: ClientComparisonService
    ):
        """_has_any_data checks specific fields; ping_reachable is NOT in the list."""
        comp = _make_comparison(old_ping_reachable=True)
        assert service._has_any_data(comp, "old") is False


# ===================================================================
# _compare_records  (integration of helpers)
# ===================================================================

class TestCompareRecords:
    """_compare_records ties together _find_differences, _generate_notes,
    and _has_any_data.  A few integration-style tests verify the overall flow.
    """

    def test_both_sides_no_data_undetected(self, service: ClientComparisonService):
        """Both old and new have no data -> severity 'undetected'."""
        comp = _make_comparison()
        result = service._compare_records(comp)
        assert result.severity == "undetected"
        assert result.is_changed is False

    def test_old_detected_new_missing(
        self, service: ClientComparisonService
    ):
        """Old has data, new does not -> is_changed True (device disappeared)."""
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            old_interface_name="GE1/0/1",
        )
        result = service._compare_records(comp)
        assert result.is_changed is True
        assert "未偵測" in result.notes

    def test_old_missing_new_detected(
        self, service: ClientComparisonService
    ):
        """Old has no data, new has data -> is_changed True (new device appeared)."""
        comp = _make_comparison(
            new_switch_hostname="SW-02",
            new_interface_name="GE1/0/1",
        )
        result = service._compare_records(comp)
        assert result.is_changed is True
        assert "未偵測" in result.notes

    def test_no_differences(self, service: ClientComparisonService):
        """Both sides identical -> is_changed False."""
        comp = _make_comparison(
            old_switch_hostname="SW-01",
            new_switch_hostname="SW-01",
            old_interface_name="GE1/0/1",
            new_interface_name="GE1/0/1",
        )
        result = service._compare_records(comp)
        assert result.is_changed is False

    def test_differences_detected(
        self, service: ClientComparisonService
    ):
        """Switch change -> is_changed True, differences populated."""
        comp = _make_comparison(
            old_switch_hostname="SW-OLD",
            new_switch_hostname="SW-NEW",
            old_interface_name="GE1/0/1",
            new_interface_name="GE1/0/1",
        )
        result = service._compare_records(comp)
        assert result.is_changed is True
        assert "switch_hostname" in result.differences
