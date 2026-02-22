"""Tests for per-MAC hash computation in ClientCollectionService."""
from unittest.mock import MagicMock

from app.services.client_collection_service import ClientCollectionService


class TestComputeClientRecordHash:
    def _make_record(self, **kwargs):
        defaults = {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "ip_address": "10.0.0.1",
            "switch_hostname": "SW-01",
            "interface_name": "GE1/0/1",
            "vlan_id": 10,
            "speed": "1G",
            "duplex": "full",
            "link_status": "up",
            "ping_reachable": True,
            "acl_rules_applied": "3001",
        }
        defaults.update(kwargs)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_same_data_same_hash(self):
        r1 = self._make_record()
        r2 = self._make_record()
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 == h2

    def test_different_data_different_hash(self):
        r1 = self._make_record(speed="1G")
        r2 = self._make_record(speed="10G")
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 != h2

    def test_hash_length_is_16(self):
        r = self._make_record()
        h = ClientCollectionService._compute_client_record_hash(r)
        assert len(h) == 16

    def test_identity_fields_excluded(self):
        """mac_address and ip_address changes should NOT change hash."""
        r1 = self._make_record(mac_address="AA:BB:CC:DD:EE:FF", ip_address="10.0.0.1")
        r2 = self._make_record(mac_address="11:22:33:44:55:66", ip_address="10.0.0.2")
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 == h2

    def test_ping_change_detected(self):
        r1 = self._make_record(ping_reachable=True)
        r2 = self._make_record(ping_reachable=False)
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 != h2

    def test_acl_change_detected(self):
        r1 = self._make_record(acl_rules_applied="3001")
        r2 = self._make_record(acl_rules_applied="3560")
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 != h2

    def test_none_values_handled(self):
        r = self._make_record(
            switch_hostname=None, interface_name=None,
            vlan_id=None, speed=None, duplex=None,
            link_status=None, ping_reachable=None,
            acl_rules_applied=None,
        )
        h = ClientCollectionService._compute_client_record_hash(r)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_none_vs_value_different_hash(self):
        r1 = self._make_record(ping_reachable=None)
        r2 = self._make_record(ping_reachable=True)
        h1 = ClientCollectionService._compute_client_record_hash(r1)
        h2 = ClientCollectionService._compute_client_record_hash(r2)
        assert h1 != h2
