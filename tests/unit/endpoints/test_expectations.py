"""
Unit tests for Expectations API endpoints.

Tests uplink, version, and port-channel expectation CRUD operations
with mocked DB sessions and service calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.expectations import router
from app.db.base import get_async_session

ROOT_USER = {
    "user_id": 1,
    "username": "root",
    "role": "ROOT",
    "maintenance_id": None,
    "display_name": "系統管理員",
    "is_root": True,
}
PM_USER = {
    "user_id": 2,
    "username": "pm1",
    "role": "PM",
    "maintenance_id": "MAINT-001",
    "display_name": "PM User",
    "is_root": False,
}
GUEST_USER = {
    "user_id": 3,
    "username": "guest1",
    "role": "GUEST",
    "maintenance_id": "MAINT-001",
    "display_name": "Guest",
    "is_root": False,
}


def _make_mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _build_app(user: dict, session: AsyncMock) -> FastAPI:
    """Build a minimal FastAPI app with auth and session overrides."""
    app = FastAPI()
    app.include_router(router)

    async def _override_current_user():
        return user

    async def _override_session():
        return session

    app.dependency_overrides[get_current_user] = _override_current_user
    # The expectations router imports get_async_session as get_session.
    # We need to override the actual dependency function used in Depends().
    # The router uses: from app.db.base import get_async_session as get_session
    # FastAPI matches dependency overrides by identity, so we override get_async_session.
    app.dependency_overrides[get_async_session] = _override_session

    return app


# ========== Mock Object Helpers ==========


def _make_uplink_obj(**kwargs):
    """Create a mock UplinkExpectation object."""
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.hostname = kwargs.get("hostname", "SW-01")
    obj.local_interface = kwargs.get("local_interface", "GigabitEthernet1/0/1")
    obj.expected_neighbor = kwargs.get("expected_neighbor", "SW-02")
    obj.expected_interface = kwargs.get("expected_interface", "GigabitEthernet1/0/1")
    obj.description = kwargs.get("description", None)
    return obj


def _make_version_obj(**kwargs):
    """Create a mock VersionExpectation object."""
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.hostname = kwargs.get("hostname", "SW-01")
    obj.expected_versions = kwargs.get("expected_versions", "16.12.4;17.3.5")
    obj.description = kwargs.get("description", None)
    return obj


def _make_port_channel_obj(**kwargs):
    """Create a mock PortChannelExpectation object."""
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.hostname = kwargs.get("hostname", "SW-01")
    obj.port_channel = kwargs.get("port_channel", "Port-channel1")
    obj.member_interfaces = kwargs.get(
        "member_interfaces", "GigabitEthernet1/0/1;GigabitEthernet1/0/2"
    )
    obj.description = kwargs.get("description", None)
    return obj


def _make_device_obj(**kwargs):
    """Create a mock MaintenanceDeviceList object for hostname validation."""
    obj = MagicMock()
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.new_hostname = kwargs.get("new_hostname", "SW-01")
    return obj


# ========== TestUplinkExpectations ==========


class TestUplinkExpectations:
    """Tests for uplink expectation CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list(self):
        """GET /uplink/MAINT-001 returns 200 with items."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_uplink_obj(id=1, hostname="SW-01")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [item]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/uplink/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "SW-01"

    @pytest.mark.asyncio
    async def test_create(self):
        """POST /uplink/MAINT-001 returns 200 with created item."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        # validate_hostname_in_device_list (2 calls: hostname + neighbor)
        device_result1 = MagicMock()
        device_result1.scalar_one_or_none.return_value = _make_device_obj(new_hostname="SW-01")
        device_result2 = MagicMock()
        device_result2.scalar_one_or_none.return_value = _make_device_obj(new_hostname="SW-02")
        # dup check (hostname + local_interface)
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None
        # topology check 1: local interface as remote
        topo1 = MagicMock()
        topo1.scalar_one_or_none.return_value = None
        # topology check 2: remote interface as local
        topo2 = MagicMock()
        topo2.scalar_one_or_none.return_value = None
        # topology check 3: remote interface as remote
        topo3 = MagicMock()
        topo3.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            device_result1,
            device_result2,
            dup_result,
            topo1,
            topo2,
            topo3,
        ]

        session.refresh.side_effect = lambda obj: setattr(obj, "id", 99)

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/uplink/MAINT-001",
                    json={
                        "hostname": "SW-01",
                        "local_interface": "GigabitEthernet1/0/3",
                        "expected_neighbor": "SW-02",
                        "expected_interface": "GigabitEthernet1/0/3",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "SW-01"
        assert data["expected_neighbor"] == "SW-02"

    @pytest.mark.asyncio
    async def test_update(self):
        """PUT /uplink/MAINT-001/{id} returns 200 with updated item."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        item = _make_uplink_obj(id=1, hostname="SW-01")

        # Find item
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = item
        # Topology check: local interface not used as remote
        topo1 = MagicMock()
        topo1.scalar_one_or_none.return_value = None
        # Topology check 2: remote as local
        topo2 = MagicMock()
        topo2.scalar_one_or_none.return_value = None
        # Topology check 3: remote as remote
        topo3 = MagicMock()
        topo3.scalar_one_or_none.return_value = None

        session.execute.side_effect = [find_result, topo1, topo2, topo3]

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/uplink/MAINT-001/1",
                    json={"description": "Updated description"},
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete(self):
        """DELETE /uplink/MAINT-001/{id} returns 200."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_uplink_obj(id=1)
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = item
        session.execute.return_value = find_result

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/uplink/MAINT-001/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_batch_delete(self):
        """POST /uplink/MAINT-001/batch-delete returns 200 with count."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        delete_result = MagicMock()
        delete_result.rowcount = 3
        session.execute.return_value = delete_result

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/uplink/MAINT-001/batch-delete",
                    json={"item_ids": [1, 2, 3]},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["deleted_count"] == 3

    @pytest.mark.asyncio
    async def test_export_csv(self):
        """GET /uplink/MAINT-001/export-csv returns 200 with CSV content."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_uplink_obj(id=1, hostname="SW-01")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [item]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/uplink/MAINT-001/export-csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        # CSV should contain the hostname
        assert "SW-01" in resp.text

    @pytest.mark.asyncio
    async def test_requires_write_for_create(self):
        """GUEST user receives 403 on create."""
        session = _make_mock_session()
        app = _build_app(GUEST_USER, session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/uplink/MAINT-001",
                json={
                    "hostname": "SW-01",
                    "local_interface": "Gi1/0/1",
                    "expected_neighbor": "SW-02",
                    "expected_interface": "Gi1/0/1",
                },
            )

        assert resp.status_code == 403


# ========== TestVersionExpectations ==========


class TestVersionExpectations:
    """Tests for version expectation CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list(self):
        """GET /version/MAINT-001 returns 200 with items."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_version_obj(id=1, hostname="SW-01", expected_versions="16.12.4;17.3.5")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [item]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/version/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "SW-01"
        assert "expected_versions_list" in data["items"][0]

    @pytest.mark.asyncio
    async def test_create(self):
        """POST /version/MAINT-001 returns 200 with created item."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        # validate_hostname_in_device_list
        device_result = MagicMock()
        device_result.scalar_one_or_none.return_value = _make_device_obj(new_hostname="SW-01")
        # dup check
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [device_result, dup_result]
        session.refresh.side_effect = lambda obj: setattr(obj, "id", 50)

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/version/MAINT-001",
                    json={
                        "hostname": "SW-01",
                        "expected_versions": "17.3.5;16.12.4",
                        "description": "Target versions",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "SW-01"
        # Versions should be sorted
        assert "16.12.4" in data["expected_versions"]

    @pytest.mark.asyncio
    async def test_delete(self):
        """DELETE /version/MAINT-001/{id} returns 200."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_version_obj(id=1)
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = item
        session.execute.return_value = find_result

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/version/MAINT-001/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"


# ========== TestPortChannelExpectations ==========


class TestPortChannelExpectations:
    """Tests for port-channel expectation CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list(self):
        """GET /port-channel/MAINT-001 returns 200 with items."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_port_channel_obj(id=1, hostname="SW-01")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [item]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute.return_value = result_mock

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/port-channel/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "SW-01"
        assert "member_interfaces_list" in data["items"][0]

    @pytest.mark.asyncio
    async def test_create(self):
        """POST /port-channel/MAINT-001 returns 200 with created item."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        # validate_hostname_in_device_list
        device_result = MagicMock()
        device_result.scalar_one_or_none.return_value = _make_device_obj(new_hostname="SW-01")
        # dup check (hostname + port_channel)
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [device_result, dup_result]
        session.refresh.side_effect = lambda obj: setattr(obj, "id", 77)

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/port-channel/MAINT-001",
                    json={
                        "hostname": "SW-01",
                        "port_channel": "Port-channel1",
                        "member_interfaces": "Gi1/0/1;Gi1/0/2",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["hostname"] == "SW-01"
        assert data["port_channel"] == "Port-channel1"

    @pytest.mark.asyncio
    async def test_delete(self):
        """DELETE /port-channel/MAINT-001/{id} returns 200."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        item = _make_port_channel_obj(id=1)
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = item
        session.execute.return_value = find_result

        with patch("app.api.endpoints.expectations.write_log", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/port-channel/MAINT-001/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
