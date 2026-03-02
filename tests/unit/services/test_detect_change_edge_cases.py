"""
Extended edge case tests for _detect_change() and case service utilities.

Focuses on type coercion, numeric edge cases, boundary conditions,
and the 15-minute grace period for - → value transitions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.case_service import _detect_change


class TestDetectChangeTypeCoercion:
    """Test string coercion edge cases in _detect_change()."""

    def test_int_vs_string_same_value(self):
        """int 1000 and str '1000' are treated as same (both str(v))."""
        assert _detect_change([1000, "1000"]) is False

    def test_int_vs_float_different_str(self):
        """int 1000 → '1000', float 1000.0 → '1000.0' — different strings!"""
        # This is an edge case — the same logical value has different string repr
        assert _detect_change([1000, 1000.0]) is True

    def test_float_same_value(self):
        """Two identical floats: no change."""
        assert _detect_change([1000.0, 1000.0]) is False

    def test_bool_true_vs_int_1(self):
        """bool True → 'True', int 1 → '1' — different."""
        assert _detect_change([True, 1]) is True

    def test_bool_false_vs_int_0(self):
        """bool False → 'False', int 0 → '0' — different."""
        assert _detect_change([False, 0]) is True

    def test_empty_string_is_not_none(self):
        """'' is not None, so it's a valid non-null value."""
        assert _detect_change(["", ""]) is False

    def test_empty_string_vs_none(self):
        """[None, ''] → transition from - to value, no timestamp → change (rule 4b)."""
        assert _detect_change([None, ""]) is True

    def test_empty_string_vs_none_settled(self):
        """[None, ''] with old timestamp → settled (rule 4a)."""
        old_ts = datetime.now(timezone.utc) - timedelta(minutes=20)
        assert _detect_change([None, ""], last_collected_at=old_ts) is False

    def test_empty_string_then_none(self):
        """['' , None] → last is None → normal (rule 3)."""
        assert _detect_change(["", None]) is False


class TestDetectChangeSequenceLength:
    """Test with various sequence lengths."""

    def test_single_none(self):
        assert _detect_change([None]) is False

    def test_very_long_stable(self):
        """100 identical values: stable."""
        assert _detect_change(["up"] * 100) is False

    def test_very_long_with_one_change(self):
        """99 'up' + 1 'down': change detected."""
        vals = ["up"] * 99 + ["down"]
        assert _detect_change(vals) is True

    def test_long_with_trailing_none(self):
        """Many values, last is None → normal (device offline, rule 3)."""
        vals = ["up"] * 50 + [None]
        assert _detect_change(vals) is False

    def test_all_none_long(self):
        """All None: no change."""
        assert _detect_change([None] * 20) is False


class TestDetectChangeRealWorldScenarios:
    """Real-world scenarios from network monitoring."""

    def test_speed_change_1g_to_100m(self):
        assert _detect_change(["1G", "1G", "100M"]) is True

    def test_speed_stable(self):
        assert _detect_change(["1G", "1G", "1G"]) is False

    def test_duplex_change(self):
        assert _detect_change(["full", "full", "half"]) is True

    def test_link_flap_up_down_up(self):
        assert _detect_change(["up", "down", "up"]) is True

    def test_vlan_change(self):
        assert _detect_change([100, 200]) is True

    def test_vlan_stable(self):
        assert _detect_change([100, 100, 100]) is False

    def test_acl_added_no_timestamp(self):
        """ACL goes from None to '101', no timestamp → change (just transitioned)."""
        assert _detect_change([None, "101"]) is True

    def test_acl_added_settled(self):
        """ACL goes from None to '101', >15 min ago → stable."""
        old_ts = datetime.now(timezone.utc) - timedelta(minutes=20)
        assert _detect_change([None, "101"], last_collected_at=old_ts) is False

    def test_acl_removed(self):
        """ACL goes from '101' to None → normal (device offline/cleared, rule 3)."""
        assert _detect_change(["101", None]) is False

    def test_acl_changed(self):
        assert _detect_change(["101", "102"]) is True

    def test_device_offline_then_back_no_timestamp(self):
        """Device: 1G → None → 1G. Transition back, no timestamp → change."""
        assert _detect_change(["1G", None, "1G"]) is True

    def test_device_offline_then_back_settled(self):
        """Device: 1G → None → 1G. >15 min old → stable."""
        old_ts = datetime.now(timezone.utc) - timedelta(minutes=20)
        assert _detect_change(["1G", None, "1G"], last_collected_at=old_ts) is False

    def test_device_offline_then_back_recent(self):
        """Device: 1G → None → 1G. <15 min → still abnormal."""
        recent_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert _detect_change(["1G", None, "1G"], last_collected_at=recent_ts) is True

    def test_device_offline_stayed_offline(self):
        """Device had value then went None and stayed None → normal (rule 3)."""
        assert _detect_change(["1G", None, None]) is False

    def test_interface_name_change(self):
        assert _detect_change(["Gi1/0/1", "Gi1/0/2"]) is True

    def test_ping_reachable_change(self):
        assert _detect_change([True, True, False]) is True

    def test_ping_always_reachable(self):
        assert _detect_change([True, True, True]) is False

    def test_mixed_types_in_snapshots(self):
        """Speed could come as int then string."""
        assert _detect_change([1000, "1000"]) is False

    def test_none_sandwich(self):
        """[None, 'up', None] → last=None → normal (rule 3)."""
        assert _detect_change([None, "up", None]) is False

    def test_all_different(self):
        assert _detect_change(["a", "b", "c", "d"]) is True

    def test_two_values_alternating(self):
        assert _detect_change(["up", "down", "up", "down"]) is True


class TestDetectChange15MinGracePeriod:
    """Test the 15-minute grace period for - → value transitions."""

    def test_just_under_15_minutes_is_change(self):
        """14 min 50 sec → still change (need > 15 min)."""
        ts = datetime.now(timezone.utc) - timedelta(minutes=14, seconds=50)
        assert _detect_change([None, "1G"], last_collected_at=ts) is True

    def test_just_over_15_minutes_is_stable(self):
        """15 min + 1 sec → stable."""
        ts = datetime.now(timezone.utc) - timedelta(minutes=15, seconds=1)
        assert _detect_change([None, "1G"], last_collected_at=ts) is False

    def test_1_hour_ago_is_stable(self):
        """1 hour old → definitely stable."""
        ts = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _detect_change([None, "1G"], last_collected_at=ts) is False

    def test_1_minute_ago_is_change(self):
        """1 min old → definitely change."""
        ts = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert _detect_change([None, "1G"], last_collected_at=ts) is True

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime (no tzinfo) treated as UTC."""
        ts = datetime.utcnow() - timedelta(minutes=20)
        assert _detect_change([None, "1G"], last_collected_at=ts) is False

    def test_no_none_in_history_ignores_timestamp(self):
        """No Nones in values → timestamp irrelevant, always stable."""
        recent_ts = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert _detect_change(["1G", "1G"], last_collected_at=recent_ts) is False

    def test_multiple_values_ignores_timestamp(self):
        """Multiple different values → always change, timestamp irrelevant."""
        old_ts = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _detect_change(["1G", "100M"], last_collected_at=old_ts) is True

    def test_last_none_ignores_timestamp(self):
        """Last is None → always normal, timestamp irrelevant."""
        recent_ts = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert _detect_change(["1G", None], last_collected_at=recent_ts) is False

    def test_no_timestamp_with_none_history(self):
        """Has Nones in history, last is value, no timestamp → change (conservative)."""
        assert _detect_change([None, None, "up"]) is True
