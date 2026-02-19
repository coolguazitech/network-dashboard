"""Tests for app.services.change_cache."""
from unittest.mock import MagicMock

from app.services.change_cache import (
    ClientChangeCache,
    IndicatorChangeCache,
    compute_client_hash,
    compute_indicator_hash,
)
from app.parsers.protocols import FanStatusData


class TestComputeIndicatorHash:
    def test_same_data_same_hash(self):
        items = [
            FanStatusData(fan_id="Fan 1/1", status="normal"),
            FanStatusData(fan_id="Fan 1/2", status="normal"),
        ]
        h1 = compute_indicator_hash(items)
        h2 = compute_indicator_hash(items)
        assert h1 == h2

    def test_different_data_different_hash(self):
        items1 = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        items2 = [FanStatusData(fan_id="Fan 1/1", status="fail")]
        assert compute_indicator_hash(items1) != compute_indicator_hash(items2)

    def test_order_independent(self):
        """Sorted before hashing, so order shouldn't matter."""
        items1 = [
            FanStatusData(fan_id="Fan 1/1", status="normal"),
            FanStatusData(fan_id="Fan 1/2", status="ok"),
        ]
        items2 = [
            FanStatusData(fan_id="Fan 1/2", status="ok"),
            FanStatusData(fan_id="Fan 1/1", status="normal"),
        ]
        assert compute_indicator_hash(items1) == compute_indicator_hash(items2)

    def test_empty_list(self):
        h = compute_indicator_hash([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex


class TestComputeClientHash:
    def _make_record(self, **kwargs):
        defaults = {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "switch_hostname": "SW-01",
            "interface_name": "GE1/0/1",
            "vlan_id": 10,
            "speed": "1G",
            "duplex": "full",
            "link_status": "up",
            "ping_reachable": True,
            "acl_passes": True,
        }
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_same_records_same_hash(self):
        r1 = self._make_record()
        r2 = self._make_record()
        h1 = compute_client_hash([r1])
        h2 = compute_client_hash([r2])
        assert h1 == h2

    def test_different_records_different_hash(self):
        r1 = self._make_record(speed="1G")
        r2 = self._make_record(speed="10G")
        assert compute_client_hash([r1]) != compute_client_hash([r2])

    def test_empty_list(self):
        h = compute_client_hash([])
        assert isinstance(h, str)
        assert len(h) == 64


class TestIndicatorChangeCache:
    def test_first_call_always_changed(self):
        cache = IndicatorChangeCache()
        items = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        assert cache.has_changed("M1", "get_fan", "SW-01", items) is True

    def test_same_data_not_changed(self):
        cache = IndicatorChangeCache()
        items = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        cache.has_changed("M1", "get_fan", "SW-01", items)
        assert cache.has_changed("M1", "get_fan", "SW-01", items) is False

    def test_different_data_changed(self):
        cache = IndicatorChangeCache()
        items1 = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        items2 = [FanStatusData(fan_id="Fan 1/1", status="fail")]
        cache.has_changed("M1", "get_fan", "SW-01", items1)
        assert cache.has_changed("M1", "get_fan", "SW-01", items2) is True

    def test_different_device_independent(self):
        cache = IndicatorChangeCache()
        items = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        cache.has_changed("M1", "get_fan", "SW-01", items)
        # Different hostname is independent
        assert cache.has_changed("M1", "get_fan", "SW-02", items) is True

    def test_clear(self):
        cache = IndicatorChangeCache()
        items = [FanStatusData(fan_id="Fan 1/1", status="normal")]
        cache.has_changed("M1", "get_fan", "SW-01", items)
        cache.clear()
        # After clear, first call should report changed again
        assert cache.has_changed("M1", "get_fan", "SW-01", items) is True


class TestClientChangeCache:
    def _make_record(self, **kwargs):
        defaults = {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "switch_hostname": "SW-01",
            "interface_name": "GE1/0/1",
            "vlan_id": 10,
            "speed": "1G",
            "duplex": "full",
            "link_status": "up",
            "ping_reachable": True,
            "acl_passes": True,
        }
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_first_call_always_changed(self):
        cache = ClientChangeCache()
        records = [self._make_record()]
        assert cache.has_changed("M1", records) is True

    def test_same_data_not_changed(self):
        cache = ClientChangeCache()
        records = [self._make_record()]
        cache.has_changed("M1", records)
        assert cache.has_changed("M1", records) is False

    def test_different_data_changed(self):
        cache = ClientChangeCache()
        r1 = [self._make_record(speed="1G")]
        r2 = [self._make_record(speed="10G")]
        cache.has_changed("M1", r1)
        assert cache.has_changed("M1", r2) is True

    def test_different_maintenance_independent(self):
        cache = ClientChangeCache()
        records = [self._make_record()]
        cache.has_changed("M1", records)
        assert cache.has_changed("M2", records) is True

    def test_clear(self):
        cache = ClientChangeCache()
        records = [self._make_record()]
        cache.has_changed("M1", records)
        cache.clear()
        assert cache.has_changed("M1", records) is True
