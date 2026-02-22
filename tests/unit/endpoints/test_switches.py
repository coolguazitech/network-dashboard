"""
Tests for app.api.endpoints.switches.

Covers:
- GET    /switches          (any authenticated user)
- POST   /switches          (write permission required)
- PUT    /switches/{id}     (write permission required)
- DELETE /switches/{id}     (write permission required)

Uses httpx.AsyncClient + ASGITransport to test routes with dependency overrides.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.switches import router
from app.db.base import get_async_session


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _create_app(user_override=None, session_override=None):
    """Build a minimal FastAPI app with the switches router and optional
    dependency overrides for authentication and database session."""
    app = FastAPI()
    app.include_router(router)
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
        # require_write() is a factory that returns a dependency function.
        # We override it so that any user with an override is treated as
        # having write permissions.
        _write_dep = require_write()
        app.dependency_overrides[_write_dep] = lambda: user_override
    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _create_app_with_write_check(user_override, session_override=None):
    """Build an app where require_write() actually checks the role.
    Used to test that GUEST users are rejected."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user_override
    # Do NOT override require_write -- let it check the role naturally.
    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _make_mock_session():
    """Create a mock AsyncSession with execute(), commit(), and related methods."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_switch_row(
    *,
    id: int = 1,
    hostname: str = "core-sw-01",
    ip_address: str = "10.0.0.1",
    vendor: str = "cisco",
    platform: str = "ios",
    site: str | None = "datacenter",
    model: str | None = "C9300-48P",
    location: str | None = "Rack A5",
    description: str | None = None,
    is_active: bool = True,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    """Create a mock object that mimics a Switch ORM row."""
    row = MagicMock()
    row.id = id
    row.hostname = hostname
    row.ip_address = ip_address
    row.vendor = vendor
    row.platform = platform
    row.site = site
    row.model = model
    row.location = location
    row.description = description
    row.is_active = is_active
    row.created_at = created_at or datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    row.updated_at = updated_at or datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    return row


# ══════════════════════════════════════════════════════════════════
# TestListSwitches
# ══════════════════════════════════════════════════════════════════


class TestListSwitches:
    """Tests for GET /switches."""

    @pytest.mark.asyncio
    async def test_list_switches_basic(self, root_user):
        """Authenticated user can list switches."""
        session = _make_mock_session()

        sw1 = _make_switch_row(id=1, hostname="sw-01", ip_address="10.0.0.1")
        sw2 = _make_switch_row(id=2, hostname="sw-02", ip_address="10.0.0.2")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [sw1, sw2]
        session.execute = AsyncMock(return_value=result_mock)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/switches")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["data"]) == 2
        assert body["data"][0]["hostname"] == "sw-01"
        assert body["data"][1]["hostname"] == "sw-02"

    @pytest.mark.asyncio
    async def test_list_switches_empty(self, root_user):
        """When no switches exist, return empty list."""
        session = _make_mock_session()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/switches")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_list_switches_guest_allowed(self, guest_user):
        """Guest users (read-only) can still list switches."""
        session = _make_mock_session()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        app = _create_app(user_override=guest_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/switches")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_switches_no_auth(self):
        """Without auth, the endpoint should return 401 (no credentials)."""
        app = _create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/switches")

        # HTTPBearer returns 401 when no Authorization header is present
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_switches_serialization(self, root_user):
        """Verify full serialization of switch fields."""
        session = _make_mock_session()

        sw = _make_switch_row(
            id=10,
            hostname="test-sw",
            ip_address="192.168.1.1",
            vendor="aruba",
            platform="aruba_cx",
            site="office",
            model="6300M",
            location="Floor 3 Rack 2",
            description="Test switch",
            is_active=False,
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [sw]
        session.execute = AsyncMock(return_value=result_mock)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/switches")

        assert resp.status_code == 200
        item = resp.json()["data"][0]
        assert item["id"] == 10
        assert item["hostname"] == "test-sw"
        assert item["ip_address"] == "192.168.1.1"
        assert item["vendor"] == "aruba"
        assert item["platform"] == "aruba_cx"
        assert item["site"] == "office"
        assert item["model"] == "6300M"
        assert item["location"] == "Floor 3 Rack 2"
        assert item["description"] == "Test switch"
        assert item["is_active"] is False
        assert "created_at" in item
        assert "updated_at" in item


# ══════════════════════════════════════════════════════════════════
# TestCreateSwitch
# ══════════════════════════════════════════════════════════════════


class TestCreateSwitch:
    """Tests for POST /switches."""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_create_switch_success(self, mock_write_log, root_user):
        """Root/PM user can create a switch."""
        session = _make_mock_session()

        # hostname uniqueness check -> no conflict
        hostname_result = MagicMock()
        hostname_result.scalar_one_or_none.return_value = None

        # IP uniqueness check -> no conflict
        ip_result = MagicMock()
        ip_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(side_effect=[hostname_result, ip_result])

        # After commit + refresh, the switch object will be serialized
        # We need refresh to set attributes on the added object
        async def mock_refresh(obj):
            obj.id = 1
            obj.hostname = "new-sw-01"
            obj.ip_address = "10.0.0.100"
            obj.vendor = "cisco"
            obj.platform = "ios"
            obj.site = "datacenter"
            obj.model = "C9300"
            obj.location = None
            obj.description = None
            obj.is_active = True
            obj.created_at = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)

        session.refresh = AsyncMock(side_effect=mock_refresh)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/switches",
                json={
                    "hostname": "new-sw-01",
                    "ip_address": "10.0.0.100",
                    "vendor": "cisco",
                    "platform": "ios",
                    "site": "datacenter",
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["hostname"] == "new-sw-01"
        assert body["data"]["ip_address"] == "10.0.0.100"

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        mock_write_log.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_create_switch_duplicate_hostname(self, mock_write_log, root_user):
        """Creating a switch with duplicate hostname returns 400."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=99, hostname="dup-sw")
        hostname_result = MagicMock()
        hostname_result.scalar_one_or_none.return_value = existing_sw

        session.execute = AsyncMock(return_value=hostname_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/switches",
                json={
                    "hostname": "dup-sw",
                    "ip_address": "10.0.0.200",
                    "vendor": "cisco",
                    "platform": "ios",
                },
            )

        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_create_switch_duplicate_ip(self, mock_write_log, root_user):
        """Creating a switch with duplicate IP returns 400."""
        session = _make_mock_session()

        # Hostname check passes
        hostname_result = MagicMock()
        hostname_result.scalar_one_or_none.return_value = None

        # IP check fails
        existing_sw = _make_switch_row(id=99, ip_address="10.0.0.200")
        ip_result = MagicMock()
        ip_result.scalar_one_or_none.return_value = existing_sw

        session.execute = AsyncMock(side_effect=[hostname_result, ip_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/switches",
                json={
                    "hostname": "unique-sw",
                    "ip_address": "10.0.0.200",
                    "vendor": "cisco",
                    "platform": "ios",
                },
            )

        assert resp.status_code == 400
        assert "IP" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_switch_guest_rejected(self, guest_user):
        """Guest user should be rejected when creating a switch (no write permission)."""
        session = _make_mock_session()

        app = _create_app_with_write_check(
            user_override=guest_user, session_override=session,
        )
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/switches",
                json={
                    "hostname": "test",
                    "ip_address": "1.2.3.4",
                    "vendor": "cisco",
                    "platform": "ios",
                },
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_switch_missing_required_fields(self, root_user):
        """Missing required fields should return 422 validation error."""
        session = _make_mock_session()

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/switches",
                json={"hostname": "only-hostname"},
            )

        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════
# TestUpdateSwitch
# ══════════════════════════════════════════════════════════════════


class TestUpdateSwitch:
    """Tests for PUT /switches/{id}."""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_update_switch_success(self, mock_write_log, root_user):
        """Root/PM user can update a switch."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=1, hostname="old-name", ip_address="10.0.0.1")

        # First execute: find switch by id
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = existing_sw

        # Second execute: hostname uniqueness check
        dup_hostname_result = MagicMock()
        dup_hostname_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(side_effect=[find_result, dup_hostname_result])

        async def mock_refresh(obj):
            obj.hostname = "new-name"

        session.refresh = AsyncMock(side_effect=mock_refresh)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/1",
                json={"hostname": "new-name"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        session.commit.assert_awaited_once()
        mock_write_log.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_update_switch_not_found(self, mock_write_log, root_user):
        """Updating a non-existent switch returns 404."""
        session = _make_mock_session()

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(return_value=find_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/999",
                json={"hostname": "does-not-matter"},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_update_switch_duplicate_hostname(self, mock_write_log, root_user):
        """Updating with a hostname that already exists on another switch returns 400."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=1, hostname="sw-01")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = existing_sw

        conflict_sw = _make_switch_row(id=2, hostname="sw-02")
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = conflict_sw

        session.execute = AsyncMock(side_effect=[find_result, dup_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/1",
                json={"hostname": "sw-02"},
            )

        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_update_switch_duplicate_ip(self, mock_write_log, root_user):
        """Updating with an IP that already exists on another switch returns 400."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=1, ip_address="10.0.0.1")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = existing_sw

        conflict_sw = _make_switch_row(id=2, ip_address="10.0.0.2")
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = conflict_sw

        session.execute = AsyncMock(side_effect=[find_result, dup_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/1",
                json={"ip_address": "10.0.0.2"},
            )

        assert resp.status_code == 400
        assert "IP" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_update_switch_partial(self, mock_write_log, root_user):
        """Partial update (only vendor) should work without triggering uniqueness checks."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=1, hostname="sw-01", vendor="cisco")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = existing_sw

        # No uniqueness checks when hostname/ip_address are not in payload
        session.execute = AsyncMock(return_value=find_result)

        async def mock_refresh(obj):
            pass  # attributes already set

        session.refresh = AsyncMock(side_effect=mock_refresh)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/1",
                json={"vendor": "aruba"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_update_switch_guest_rejected(self, guest_user):
        """Guest user should not be able to update switches."""
        session = _make_mock_session()

        app = _create_app_with_write_check(
            user_override=guest_user, session_override=session,
        )
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/switches/1",
                json={"vendor": "aruba"},
            )

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# TestDeleteSwitch
# ══════════════════════════════════════════════════════════════════


class TestDeleteSwitch:
    """Tests for DELETE /switches/{id}."""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_delete_switch_success(self, mock_write_log, root_user):
        """Root/PM user can delete a switch."""
        session = _make_mock_session()

        existing_sw = _make_switch_row(id=1, hostname="doomed-sw")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = existing_sw

        session.execute = AsyncMock(return_value=find_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/switches/1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "交換機已刪除"

        session.delete.assert_awaited_once_with(existing_sw)
        session.commit.assert_awaited_once()

        # write_log was called with WARNING level
        mock_write_log.assert_awaited_once()
        call_kwargs = mock_write_log.call_args.kwargs
        assert call_kwargs["level"] == "WARNING"
        assert "doomed-sw" in call_kwargs["summary"]

    @pytest.mark.asyncio
    @patch("app.api.endpoints.switches.write_log", new_callable=AsyncMock)
    async def test_delete_switch_not_found(self, mock_write_log, root_user):
        """Deleting a non-existent switch returns 404."""
        session = _make_mock_session()

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(return_value=find_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/switches/999")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_switch_guest_rejected(self, guest_user):
        """Guest user should not be able to delete switches."""
        session = _make_mock_session()

        app = _create_app_with_write_check(
            user_override=guest_user, session_override=session,
        )
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/switches/1")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_switch_no_auth(self):
        """Without auth, delete should return 401 (no credentials)."""
        app = _create_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/switches/1")

        # HTTPBearer returns 401 when no Authorization header is present
        assert resp.status_code == 401
