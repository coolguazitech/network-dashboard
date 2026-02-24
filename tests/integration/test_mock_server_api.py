"""Integration tests for mock server HTTP API.

Tests the production-faithful FNA / DNA / GNMS Ping routes
using FastAPI TestClient (no real HTTP needed).
"""
import pytest
from fastapi.testclient import TestClient

from mock_server.main import app, FNA_ROUTES, DNA_ROUTES


@pytest.fixture
def client():
    """Test client for mock server."""
    return TestClient(app)


# ── Health ───────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "3.0.0"
        assert "apis" in data
        assert len(data["apis"]) >= 10
        assert data["fna_routes"] == list(FNA_ROUTES.values())
        assert data["dna_routes"] == len(DNA_ROUTES)


# ── FNA Routes ───────────────────────────────────────────────────────

class TestFnaRoutes:
    """Test FNA-style routes: GET /switch/network/{command}/{switch_ip}."""

    @pytest.mark.parametrize("path,api_name", [
        ("/switch/network/get_gbic_details/10.0.0.1", "get_gbic_details"),
        ("/switch/network/get_channel_group/10.0.0.1", "get_channel_group"),
        ("/switch/network/get_interface_error_count/10.0.0.1", "get_error_count"),
        ("/switch/network/get_static_acl/10.0.0.1", "get_static_acl"),
        ("/switch/network/get_dynamic_acl/10.0.0.1", "get_dynamic_acl"),
    ])
    def test_fna_returns_200(self, client, path, api_name):
        resp = client.get(
            path,
            params={"device_type": "hpe", "maintenance_id": "TEST-001"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert resp.status_code in (200, 504)
        if resp.status_code == 200:
            assert len(resp.text) > 0
            assert "text/plain" in resp.headers["content-type"]

    @pytest.mark.parametrize("device_type", ["hpe", "ios", "nxos"])
    def test_fna_device_types(self, client, device_type):
        resp = client.get(
            "/switch/network/get_gbic_details/10.0.0.1",
            params={"device_type": device_type, "maintenance_id": "TEST-001"},
        )
        assert resp.status_code in (200, 504)

    def test_fna_accepts_bearer_token(self, client):
        """FNA endpoints accept Authorization header without error."""
        resp = client.get(
            "/switch/network/get_gbic_details/10.0.0.1",
            params={"device_type": "hpe", "maintenance_id": "TEST-001"},
            headers={"Authorization": "Bearer some-real-token"},
        )
        assert resp.status_code in (200, 504)

    def test_fna_works_without_bearer_token(self, client):
        """Mock FNA does not enforce auth — works without token too."""
        resp = client.get(
            "/switch/network/get_gbic_details/10.0.0.1",
            params={"device_type": "hpe", "maintenance_id": "TEST-001"},
        )
        assert resp.status_code in (200, 504)

    def test_fna_works_without_maintenance_id(self, client):
        """maintenance_id is optional (defaults to empty)."""
        resp = client.get(
            "/switch/network/get_gbic_details/10.0.0.1",
            params={"device_type": "hpe"},
        )
        assert resp.status_code in (200, 504)


# ── DNA Routes ───────────────────────────────────────────────────────

class TestDnaRoutes:
    """Test DNA-style routes: GET /api/v1/{dtype}/{category}/{cmd}?hosts={ip}."""

    @pytest.mark.parametrize("path,device_type", [
        # get_fan
        ("/api/v1/hpe/environment/display_fan", "hpe"),
        ("/api/v1/ios/environment/show_env_fan", "ios"),
        ("/api/v1/nxos/environment/show_environment_fan", "nxos"),
        # get_power
        ("/api/v1/hpe/environment/display_power", "hpe"),
        ("/api/v1/ios/environment/show_env_power", "ios"),
        ("/api/v1/nxos/environment/show_environment_power", "nxos"),
        # get_version
        ("/api/v1/hpe/version/display_version", "hpe"),
        ("/api/v1/ios/version/show_version", "ios"),
        ("/api/v1/nxos/version/show_version", "nxos"),
        # get_mac_table
        ("/api/v1/hpe/macaddress/display_macaddress", "hpe"),
        ("/api/v1/ios/macaddress/show_mac_address_table", "ios"),
        ("/api/v1/nxos/macaddress/show_mac_address_table", "nxos"),
        # get_interface_status
        ("/api/v1/hpe/interface/display_interface_brief", "hpe"),
        ("/api/v1/ios/interface/show_interface_status", "ios"),
        ("/api/v1/nxos/interface/show_interface_status", "nxos"),
        # get_uplink_lldp
        ("/api/v1/hpe/neighbor/display_lldp_neighbor-information_list", "hpe"),
        ("/api/v1/ios/neighbor/show_lldp_neighbors", "ios"),
        ("/api/v1/nxos/neighbor/show_lldp_neighbors", "nxos"),
        # get_uplink_cdp (no HPE)
        ("/api/v1/ios/neighbor/show_cdp_neighbors", "ios"),
        ("/api/v1/nxos/neighbor/show_cdp_neighbors", "nxos"),
    ])
    def test_dna_returns_200(self, client, path, device_type):
        resp = client.get(path, params={"hosts": "10.0.0.1"})
        assert resp.status_code in (200, 504)
        if resp.status_code == 200:
            assert len(resp.text) > 0
            assert "text/plain" in resp.headers["content-type"]

    def test_dna_requires_hosts_param(self, client):
        """DNA endpoints require ?hosts= query param."""
        resp = client.get("/api/v1/hpe/environment/display_fan")
        assert resp.status_code == 422

    def test_dna_route_count(self):
        """Verify we have all 20 DNA routes registered."""
        assert len(DNA_ROUTES) == 20


# ── GNMS Ping ────────────────────────────────────────────────────────

class TestGnmsPing:
    """Test GNMS Ping POST endpoint."""

    def test_gnms_ping_post(self, client):
        resp = client.post(
            "/api/v1/ping",
            json={
                "app_name": "network_change_orchestrator",
                "token": "mock-token",
                "addresses": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            },
        )
        assert resp.status_code == 200
        assert "IP,Reachable,Latency_ms" in resp.text

    def test_gnms_ping_empty_addresses(self, client):
        resp = client.post(
            "/api/v1/ping",
            json={"app_name": "test", "token": "x", "addresses": []},
        )
        assert resp.status_code == 200


# ── Legacy ───────────────────────────────────────────────────────────

class TestLegacy:
    """Legacy and backward-compat endpoints."""

    def test_ping_batch_still_works(self, client):
        """ping_batch has its own standalone route."""
        resp = client.get(
            "/api/ping_batch",
            params={"switch_ip": "10.0.0.1", "maintenance_id": "TEST-001"},
        )
        assert resp.status_code == 200

    def test_old_unified_endpoint_removed(self, client):
        """Old /api/{api_name} unified endpoint should be gone."""
        resp = client.get(
            "/api/get_fan",
            params={
                "switch_ip": "10.0.0.1",
                "device_type": "hpe",
                "maintenance_id": "TEST-001",
            },
        )
        # Should NOT match the old unified route
        assert resp.status_code in (404, 405, 422)
