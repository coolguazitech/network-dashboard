"""
Unit tests for MAC List (Client List) API endpoints.

Tests cover:
- list clients, detailed list
- stats
- add / update / delete / batch-delete
- CSV export / import
"""
from __future__ import annotations

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.mac_list import router
from app.core.enums import TenantGroup, ClientDetectionStatus

# ── User payloads ──────────────────────────────────────────────

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

# ── Helpers ────────────────────────────────────────────────────


def _make_client_row(
    id: int = 1,
    mac: str = "AA:BB:CC:DD:EE:01",
    ip: str = "192.168.1.100",
    maintenance_id: str = "MAINT-001",
    tenant_group: TenantGroup = TenantGroup.F18,
    detection_status: ClientDetectionStatus = ClientDetectionStatus.NOT_CHECKED,
    description: str | None = None,
    default_assignee: str | None = "系統管理員",
) -> MagicMock:
    """Create a mock MaintenanceMacList row."""
    row = MagicMock()
    row.id = id
    row.mac_address = mac
    row.ip_address = ip
    row.maintenance_id = maintenance_id
    row.tenant_group = tenant_group
    row.detection_status = detection_status
    row.description = description
    row.default_assignee = default_assignee
    return row


def _build_app(user: dict) -> FastAPI:
    """Build a minimal FastAPI app with the mac-list router and auth override."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _mock_session_context(session_mock):
    """
    Return a context-manager factory that yields *session_mock*.

    Used to patch ``app.api.endpoints.mac_list.get_session_context``.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        yield session_mock

    return _ctx


# ── scalars().all() helper ─────────────────────────────────────


def _scalars_all(rows):
    """Configure a mock session.execute() result so .scalars().all() works."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _scalar_one_or_none(value):
    """Configure a mock session.execute() result so .scalar_one_or_none() works."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar(value):
    """Configure a mock session.execute() result so .scalar() works."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _fetchall(rows):
    """Configure a mock session.execute() result so .fetchall() works."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


# ══════════════════════════════════════════════════════════════════
# TestListClients
# ══════════════════════════════════════════════════════════════════


class TestListClients:
    """GET /api/mac-list/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_list_success(self):
        """Mock session returning client rows -> 200."""
        rows = [_make_client_row(id=1), _make_client_row(id=2, mac="AA:BB:CC:DD:EE:02", ip="192.168.1.101")]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalars_all(rows))

        app = _build_app(ROOT_USER)
        with patch(
            "app.api.endpoints.mac_list.get_session_context",
            return_value=_mock_session_context(session)(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/mac-list/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["mac_address"] == "AA:BB:CC:DD:EE:01"

    @pytest.mark.anyio
    async def test_list_detailed(self):
        """GET /mac-list/MAINT-001/detailed -> 200."""
        row = _make_client_row()
        session = AsyncMock()

        # The detailed endpoint query order:
        # 1. categories query -> scalars().all()   (determines filter)
        # 2. main client query -> scalars().all()
        # 3. (skipped: member query, because cat_ids is empty)
        # 4. ping status query -> rows  (because mac_addresses is non-empty)
        ping_result = MagicMock()
        ping_result.__iter__ = MagicMock(return_value=iter([]))

        session.execute = AsyncMock(
            side_effect=[
                _scalars_all([]),          # categories (empty)
                _scalars_all([row]),       # clients
                ping_result,              # ping status (empty)
            ]
        )

        app = _build_app(ROOT_USER)
        with patch(
            "app.api.endpoints.mac_list.get_session_context",
            return_value=_mock_session_context(session)(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/mac-list/MAINT-001/detailed")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["mac_address"] == "AA:BB:CC:DD:EE:01"


# ══════════════════════════════════════════════════════════════════
# TestGetStats
# ══════════════════════════════════════════════════════════════════


class TestGetStats:
    """GET /api/mac-list/{maintenance_id}/stats"""

    @pytest.mark.anyio
    async def test_stats(self):
        """Mock session -> 200 with total count."""
        row1 = _make_client_row(id=1, detection_status=ClientDetectionStatus.DETECTED)
        row2 = _make_client_row(id=2, mac="AA:BB:CC:DD:EE:02", detection_status=ClientDetectionStatus.NOT_CHECKED)
        session = AsyncMock()

        # Calls: 1) client list, 2) categories, 3) (no members query if cat_ids empty)
        session.execute = AsyncMock(
            side_effect=[
                _scalars_all([row1, row2]),  # clients
                _fetchall([]),               # category IDs (empty)
            ]
        )

        app = _build_app(ROOT_USER)
        with patch(
            "app.api.endpoints.mac_list.get_session_context",
            return_value=_mock_session_context(session)(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/mac-list/MAINT-001/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["detected"] == 1
        assert body["not_checked"] == 1


# ══════════════════════════════════════════════════════════════════
# TestAddClient
# ══════════════════════════════════════════════════════════════════


class TestAddClient:
    """POST /api/mac-list/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_add_success(self):
        """POST with mac/ip -> 200."""
        session = AsyncMock()

        # Build a mock entry that will be returned after commit+refresh
        entry = _make_client_row(id=10)

        # Calls:
        # 1. check existing MAC -> scalar_one_or_none (None)
        # 2. resolve_default_assignee -> select ROOT user -> first()
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),      # MAC not existing
                MagicMock(first=MagicMock(return_value=("系統管理員",))),  # ROOT user display_name
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()
        # After refresh, the entry should have an id
        async def _refresh(obj):
            obj.id = 10
            obj.mac_address = "AA:BB:CC:DD:EE:01"
            obj.ip_address = "192.168.1.100"
            obj.tenant_group = TenantGroup.F18
            obj.detection_status = ClientDetectionStatus.NOT_CHECKED
            obj.description = None
            obj.default_assignee = "系統管理員"
            obj.maintenance_id = "MAINT-001"

        session.refresh = AsyncMock(side_effect=_refresh)

        app = _build_app(ROOT_USER)
        with (
            patch(
                "app.api.endpoints.mac_list.get_session_context",
                return_value=_mock_session_context(session)(),
            ),
            patch("app.api.endpoints.mac_list.write_log", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.regenerate_comparisons", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/mac-list/MAINT-001",
                    json={
                        "mac_address": "AA:BB:CC:DD:EE:01",
                        "ip_address": "192.168.1.100",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["mac_address"] == "AA:BB:CC:DD:EE:01"
        assert body["ip_address"] == "192.168.1.100"

    @pytest.mark.anyio
    async def test_add_requires_write(self):
        """GUEST user -> 403 on POST."""
        app = _build_app(GUEST_USER)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/mac-list/MAINT-001",
                json={
                    "mac_address": "AA:BB:CC:DD:EE:01",
                    "ip_address": "192.168.1.100",
                },
            )

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# TestUpdateClient
# ══════════════════════════════════════════════════════════════════


class TestUpdateClient:
    """PUT /api/mac-list/{maintenance_id}/{client_id}"""

    @pytest.mark.anyio
    async def test_update_success(self):
        """PUT -> 200."""
        existing = _make_client_row(id=5)
        session = AsyncMock()

        # Calls:
        # 1. find client by maintenance_id + client_id -> scalar_one_or_none
        session.execute = AsyncMock(
            return_value=_scalar_one_or_none(existing),
        )
        session.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = 5
            obj.mac_address = "AA:BB:CC:DD:EE:01"
            obj.ip_address = "10.0.0.1"
            obj.tenant_group = TenantGroup.F18
            obj.detection_status = ClientDetectionStatus.NOT_CHECKED
            obj.description = "updated"
            obj.default_assignee = "系統管理員"
            obj.maintenance_id = "MAINT-001"

        session.refresh = AsyncMock(side_effect=_refresh)

        app = _build_app(PM_USER)
        with (
            patch(
                "app.api.endpoints.mac_list.get_session_context",
                return_value=_mock_session_context(session)(),
            ),
            patch("app.api.endpoints.mac_list.write_log", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.regenerate_comparisons", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/mac-list/MAINT-001/5",
                    json={"ip_address": "10.0.0.1", "description": "updated"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ip_address"] == "10.0.0.1"


# ══════════════════════════════════════════════════════════════════
# TestDeleteClient
# ══════════════════════════════════════════════════════════════════


class TestDeleteClient:
    """DELETE /api/mac-list/{maintenance_id}/{mac_address} and batch-delete."""

    @pytest.mark.anyio
    async def test_delete_by_mac(self):
        """DELETE -> 200."""
        existing = _make_client_row(id=1)
        session = AsyncMock()

        # Calls:
        # 1. find MAC -> scalar_one_or_none
        # 2. get category IDs -> fetchall
        # 3. session.delete()
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(existing),   # find entry
                _fetchall([]),                    # category IDs (none)
            ]
        )
        session.delete = AsyncMock()
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        with (
            patch(
                "app.api.endpoints.mac_list.get_session_context",
                return_value=_mock_session_context(session)(),
            ),
            patch("app.api.endpoints.mac_list.write_log", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.regenerate_comparisons", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete("/api/mac-list/MAINT-001/AA:BB:CC:DD:EE:01")

        assert resp.status_code == 200
        body = resp.json()
        assert "已移除" in body["message"]

    @pytest.mark.anyio
    async def test_batch_delete(self):
        """POST batch-delete -> 200."""
        session = AsyncMock()

        # Calls:
        # 1. get MAC addresses for IDs -> fetchall
        # 2. get category IDs -> fetchall
        # 3. delete member records -> execute
        # 4. delete MAC records -> execute (with rowcount)
        mac_result = MagicMock()
        mac_result.fetchall.return_value = [("AA:BB:CC:DD:EE:01",)]

        cat_result = MagicMock()
        cat_result.fetchall.return_value = []

        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute = AsyncMock(
            side_effect=[
                mac_result,       # macs to delete
                cat_result,       # category IDs (none)
                delete_result,    # delete MaintenanceMacList
            ]
        )
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        with (
            patch(
                "app.api.endpoints.mac_list.get_session_context",
                return_value=_mock_session_context(session)(),
            ),
            patch("app.api.endpoints.mac_list.write_log", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.regenerate_comparisons", new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/mac-list/MAINT-001/batch-delete",
                    json={"mac_ids": [1]},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["deleted_count"] == 1


# ══════════════════════════════════════════════════════════════════
# TestImportExportCsv
# ══════════════════════════════════════════════════════════════════


class TestImportExportCsv:
    """CSV import/export endpoints."""

    @pytest.mark.anyio
    async def test_export_csv(self):
        """GET export-csv -> 200 with CSV content type."""
        row = _make_client_row()
        session = AsyncMock()

        # export_csv: 1) select clients, potentially category queries
        session.execute = AsyncMock(return_value=_scalars_all([row]))

        app = _build_app(ROOT_USER)
        with patch(
            "app.api.endpoints.mac_list.get_session_context",
            return_value=_mock_session_context(session)(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/mac-list/MAINT-001/export-csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        # Body should contain the CSV header and data
        body_text = resp.text
        assert "mac_address" in body_text
        assert "AA:BB:CC:DD:EE:01" in body_text

    @pytest.mark.anyio
    async def test_import_csv(self):
        """POST import-csv with file -> 200 with counts."""
        session = AsyncMock()

        # CSV content
        csv_content = (
            "mac_address,ip_address,tenant_group,description,default_assignee\n"
            "AA:BB:CC:DD:EE:01,192.168.1.100,F18,test,\n"
        )

        # Calls during import:
        # 1. check existing MAC -> scalar_one_or_none (None)
        # 2. resolve_default_assignee -> ROOT user display_name
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),    # MAC not existing
                MagicMock(first=MagicMock(return_value=("系統管理員",))),  # ROOT user
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        with (
            patch(
                "app.api.endpoints.mac_list.get_session_context",
                return_value=_mock_session_context(session)(),
            ),
            patch("app.api.endpoints.mac_list.write_log", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.regenerate_comparisons", new_callable=AsyncMock),
            patch("app.api.endpoints.mac_list.CaseService", create=True) as MockCaseService,
        ):
            # Mock CaseService used inside import_csv
            mock_case_svc = AsyncMock()
            mock_case_svc.sync_cases = AsyncMock()
            # Patch the import inside the function
            with patch(
                "app.services.case_service.CaseService",
                return_value=mock_case_svc,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/mac-list/MAINT-001/import-csv",
                        files={"file": ("test.csv", csv_content.encode(), "text/csv")},
                    )

        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 1
        assert body["skipped"] == 0
