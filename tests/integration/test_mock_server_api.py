"""Integration tests for mock server HTTP API.

Tests the actual FastAPI app using TestClient (no real HTTP needed).
"""
import pytest
from fastapi.testclient import TestClient

from mock_server.main import app


@pytest.fixture
def client():
    """Test client for mock server."""
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "apis" in data
        assert len(data["apis"]) >= 10


class TestMockApiEndpoint:
    """Test the unified /api/{api_name} endpoint."""

    @pytest.mark.parametrize("api_name", [
        "get_gbic_details",
        "get_channel_group",
        "get_uplink",
        "get_error_count",
        "get_static_acl",
        "get_dynamic_acl",
        "get_mac_table",
        "get_fan",
        "get_power",
        "get_version",
        "get_interface_status",
    ])
    def test_api_returns_200(self, client, api_name):
        resp = client.get(
            f"/api/{api_name}",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
            },
        )
        # Either 200 (success) or 504 (device unreachable) are valid
        assert resp.status_code in (200, 504)
        if resp.status_code == 200:
            assert len(resp.text) > 0

    @pytest.mark.parametrize("device_type", ["hpe", "ios", "nxos"])
    def test_device_types(self, client, device_type):
        resp = client.get(
            "/api/get_fan",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": device_type,
                "maintenance_id": "TEST-001",
            },
        )
        assert resp.status_code in (200, 504)

    def test_unknown_api_returns_404(self, client):
        resp = client.get(
            "/api/nonexistent_api",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
            },
        )
        assert resp.status_code == 404
        assert "Unknown API" in resp.text

    def test_ping_batch_always_available(self, client):
        """Ping is exempt from reachability — always returns 200."""
        resp = client.get(
            "/api/ping_batch",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
            },
        )
        assert resp.status_code == 200

    def test_gnms_ping_with_switch_ips(self, client):
        resp = client.get(
            "/api/gnms_ping",
            params={
                "switch_ip": "0.0.0.0",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
                "switch_ips": "10.0.0.1,10.0.0.2,10.0.0.3",
            },
        )
        assert resp.status_code == 200
        assert "IP,Reachable,Latency_ms" in resp.text

    def test_content_type_is_text_plain(self, client):
        resp = client.get(
            "/api/get_version",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
            },
        )
        if resp.status_code == 200:
            assert "text/plain" in resp.headers["content-type"]
