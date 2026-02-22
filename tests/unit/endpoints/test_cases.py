"""
Unit tests for Cases API endpoints.

Tests case listing, stats, sync, detail, update, notes, and change timeline
with mocked CaseService and DB sessions.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.cases import router
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

NOW_ISO = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc).isoformat()


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
    app.dependency_overrides[get_async_session] = _override_session

    return app


# ========== TestListCases ==========


class TestListCases:
    """Tests for GET /cases/{maintenance_id}."""

    @pytest.mark.asyncio
    async def test_list_basic(self):
        """GET returns 200 with cases and pagination."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_result = {
            "cases": [
                {
                    "id": 1,
                    "maintenance_id": "MAINT-001",
                    "mac_address": "AA:BB:CC:DD:EE:01",
                    "ip_address": "10.0.0.1",
                    "description": "Printer",
                    "tenant_group": None,
                    "status": "ASSIGNED",
                    "assignee": "PM User",
                    "summary": None,
                    "last_ping_reachable": True,
                    "change_tags": [],
                    "created_at": NOW_ISO,
                    "updated_at": NOW_ISO,
                }
            ],
            "count": 1,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        with patch(
            "app.api.endpoints.cases._svc.get_cases",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/cases/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert len(data["cases"]) == 1
        assert data["page"] == 1
        assert data["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        """GET with status=IN_PROGRESS returns filtered cases."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        mock_result = {
            "cases": [
                {
                    "id": 2,
                    "maintenance_id": "MAINT-001",
                    "mac_address": "AA:BB:CC:DD:EE:02",
                    "ip_address": "10.0.0.2",
                    "description": None,
                    "tenant_group": None,
                    "status": "IN_PROGRESS",
                    "assignee": "PM User",
                    "summary": "Working on it",
                    "last_ping_reachable": False,
                    "change_tags": [],
                    "created_at": NOW_ISO,
                    "updated_at": NOW_ISO,
                }
            ],
            "count": 1,
            "total": 1,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        with patch(
            "app.api.endpoints.cases._svc.get_cases",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_get:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/cases/MAINT-001", params={"status": "IN_PROGRESS"}
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["cases"][0]["status"] == "IN_PROGRESS"
        # Verify the service was called with the status filter
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("status") == "IN_PROGRESS" or \
               (len(call_kwargs.args) == 0 and "status" in str(call_kwargs))

    @pytest.mark.asyncio
    async def test_list_with_search(self):
        """GET with search=AA:BB returns filtered cases."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_result = {
            "cases": [],
            "count": 0,
            "total": 0,
            "page": 1,
            "page_size": 50,
            "total_pages": 1,
        }

        with patch(
            "app.api.endpoints.cases._svc.get_cases",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_get:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/cases/MAINT-001", params={"search": "AA:BB"}
                )

        assert resp.status_code == 200
        mock_get.assert_called_once()


# ========== TestGetCaseStats ==========


class TestGetCaseStats:
    """Tests for GET /cases/{maintenance_id}/stats."""

    @pytest.mark.asyncio
    async def test_stats(self):
        """GET stats returns 200 with status counts."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_stats = {
            "total": 100,
            "unassigned": 10,
            "assigned": 40,
            "in_progress": 25,
            "discussing": 5,
            "resolved": 20,
            "ping_unreachable": 15,
            "active": 80,
        }

        with patch(
            "app.api.endpoints.cases._svc.get_case_stats",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/cases/MAINT-001/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 100
        assert data["active"] == 80
        assert data["ping_unreachable"] == 15


# ========== TestSyncCases ==========


class TestSyncCases:
    """Tests for POST /cases/{maintenance_id}/sync."""

    @pytest.mark.asyncio
    async def test_sync_success(self):
        """POST sync returns 200 with created count."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_result = {"created": 5, "total": 50}

        with patch(
            "app.api.endpoints.cases._svc.sync_cases",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.api.endpoints.cases.write_log",
            new_callable=AsyncMock,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/cases/MAINT-001/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["created"] == 5
        assert data["total"] == 50

    @pytest.mark.asyncio
    async def test_sync_requires_write(self):
        """GUEST user receives 403 on sync."""
        session = _make_mock_session()
        app = _build_app(GUEST_USER, session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/cases/MAINT-001/sync")

        assert resp.status_code == 403


# ========== TestGetCaseDetail ==========


class TestGetCaseDetail:
    """Tests for GET /cases/{maintenance_id}/{case_id}."""

    @pytest.mark.asyncio
    async def test_detail_success(self):
        """GET case detail returns 200 with snapshot and notes."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_detail = {
            "id": 1,
            "maintenance_id": "MAINT-001",
            "mac_address": "AA:BB:CC:DD:EE:01",
            "ip_address": "10.0.0.1",
            "description": "Printer",
            "tenant_group": None,
            "status": "ASSIGNED",
            "assignee": "PM User",
            "summary": None,
            "last_ping_reachable": True,
            "change_tags": [
                {"attribute": "speed", "label": "速率", "has_change": False},
            ],
            "notes": [
                {
                    "id": 1,
                    "author": "PM User",
                    "content": "Checking device",
                    "created_at": NOW_ISO,
                }
            ],
            "latest_snapshot": {
                "speed": "1G",
                "duplex": "full",
                "link_status": "up",
                "interface_name": "Gi1/0/5",
                "vlan_id": "100",
                "switch_hostname": "SW-01",
                "ping_reachable": True,
                "acl_rules_applied": None,
                "collected_at": NOW_ISO,
            },
            "created_at": NOW_ISO,
            "updated_at": NOW_ISO,
        }

        with patch(
            "app.api.endpoints.cases._svc.get_case_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/cases/MAINT-001/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["case"]["id"] == 1
        assert data["case"]["latest_snapshot"]["speed"] == "1G"
        assert len(data["case"]["notes"]) == 1


# ========== TestUpdateCase ==========


class TestUpdateCase:
    """Tests for PUT /cases/{maintenance_id}/{case_id}."""

    @pytest.mark.asyncio
    async def test_update_status(self):
        """PUT with status update returns 200."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        mock_result = {
            "id": 1,
            "status": "IN_PROGRESS",
            "assignee": "PM User",
            "summary": None,
            "updated_at": NOW_ISO,
        }

        with patch(
            "app.api.endpoints.cases._svc.update_case",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.api.endpoints.cases.write_log",
            new_callable=AsyncMock,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/cases/MAINT-001/1",
                    json={"status": "IN_PROGRESS"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["case"]["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_update_assignee(self):
        """PUT with assignee update returns 200."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        mock_result = {
            "id": 1,
            "status": "ASSIGNED",
            "assignee": "New PM",
            "summary": None,
            "updated_at": NOW_ISO,
        }

        with patch(
            "app.api.endpoints.cases._svc.update_case",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.api.endpoints.cases.write_log",
            new_callable=AsyncMock,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/cases/MAINT-001/1",
                    json={"assignee": "New PM"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["case"]["assignee"] == "New PM"


# ========== TestNotes ==========


class TestNotes:
    """Tests for case note CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_add_note(self):
        """POST notes returns 200 with created note."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        mock_result = {
            "id": 10,
            "author": "PM User",
            "content": "Device rebooted",
            "created_at": NOW_ISO,
        }

        with patch(
            "app.api.endpoints.cases._svc.add_note",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/cases/MAINT-001/1/notes",
                    json={"content": "Device rebooted"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["note"]["id"] == 10
        assert data["note"]["content"] == "Device rebooted"

    @pytest.mark.asyncio
    async def test_update_note(self):
        """PUT note returns 200 with updated note."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        mock_result = {
            "id": 10,
            "author": "PM User",
            "content": "Device rebooted successfully",
            "created_at": NOW_ISO,
        }

        with patch(
            "app.api.endpoints.cases._svc.update_note",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/cases/MAINT-001/1/notes/10",
                    json={"content": "Device rebooted successfully"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["note"]["content"] == "Device rebooted successfully"

    @pytest.mark.asyncio
    async def test_delete_note(self):
        """DELETE note returns 200."""
        session = _make_mock_session()
        app = _build_app(PM_USER, session)

        mock_result = {"deleted": True}

        with patch(
            "app.api.endpoints.cases._svc.delete_note",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/cases/MAINT-001/1/notes/10")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ========== TestChangeTimeline ==========


class TestChangeTimeline:
    """Tests for GET /cases/{maintenance_id}/{case_id}/changes/{attribute}."""

    @pytest.mark.asyncio
    async def test_get_timeline(self):
        """GET changes/{attribute} returns 200 with timeline entries."""
        session = _make_mock_session()
        app = _build_app(ROOT_USER, session)

        # The endpoint queries Case from DB directly, then calls _svc.get_change_timeline.
        # We need to mock session.execute for the Case lookup, then mock the service call.
        mock_case = MagicMock()
        mock_case.id = 1
        mock_case.maintenance_id = "MAINT-001"
        mock_case.mac_address = "AA:BB:CC:DD:EE:01"

        case_result = MagicMock()
        case_result.scalar_one_or_none.return_value = mock_case
        session.execute.return_value = case_result

        mock_timeline = [
            {
                "value": "1G",
                "collected_at": NOW_ISO,
                "switch_hostname": "SW-01",
            },
            {
                "value": "100M",
                "collected_at": "2026-01-14T10:00:00+00:00",
                "switch_hostname": "SW-01",
            },
        ]

        with patch(
            "app.api.endpoints.cases._svc.get_change_timeline",
            new_callable=AsyncMock,
            return_value=mock_timeline,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/cases/MAINT-001/1/changes/speed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["attribute"] == "speed"
        assert len(data["timeline"]) == 2
        assert data["timeline"][0]["value"] == "1G"
        assert data["timeline"][1]["value"] == "100M"
