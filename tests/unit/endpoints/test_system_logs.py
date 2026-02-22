"""
Tests for app.api.endpoints.system_logs.

Covers:
- POST /system-logs/frontend-error (any authenticated user)
- GET  /system-logs (root only, paginated, filtered)
- GET  /system-logs/stats (root only, level counts)
- DELETE /system-logs/cleanup (root only, retain_days)

Uses httpx.AsyncClient + ASGITransport to test routes with dependency overrides.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user, require_root
from app.api.endpoints.system_logs import router
from app.db.base import get_async_session


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _create_app(user_override=None, session_override=None, root_override=None):
    """Build a minimal FastAPI app with the system-logs router and optional
    dependency overrides for authentication and database session."""
    app = FastAPI()
    app.include_router(router)
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
    if root_override is not None:
        app.dependency_overrides[require_root] = lambda: root_override
    elif user_override is not None:
        # Default: root override follows user override so root-protected
        # endpoints accept the same user payload.
        app.dependency_overrides[require_root] = lambda: user_override
    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _make_mock_session():
    """Create a mock AsyncSession with execute() and commit()."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_log_row(
    *,
    id: int = 1,
    level: str = "ERROR",
    source: str = "api",
    module: str | None = "auth",
    summary: str = "Something happened",
    detail: str | None = None,
    user_id: int | None = None,
    username: str | None = None,
    maintenance_id: str | None = None,
    request_path: str | None = "/api/v1/test",
    request_method: str | None = "GET",
    status_code: int | None = 500,
    ip_address: str | None = "127.0.0.1",
    created_at: datetime | None = None,
):
    """Create a mock object that mimics a SystemLog ORM row."""
    row = MagicMock()
    row.id = id
    row.level = level
    row.source = source
    row.module = module
    row.summary = summary
    row.detail = detail
    row.user_id = user_id
    row.username = username
    row.maintenance_id = maintenance_id
    row.request_path = request_path
    row.request_method = request_method
    row.status_code = status_code
    row.ip_address = ip_address
    row.created_at = created_at or datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    return row


# ══════════════════════════════════════════════════════════════════
# TestFrontendError
# ══════════════════════════════════════════════════════════════════


class TestFrontendError:
    """Tests for POST /system-logs/frontend-error."""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.system_logs.write_log", new_callable=AsyncMock)
    async def test_report_error_success(self, mock_write_log):
        """Any authenticated user can report a frontend error and get 200."""
        user = {
            "user_id": 5,
            "username": "guest1",
            "role": "GUEST",
            "maintenance_id": "MAINT-001",
        }
        app = _create_app(user_override=user)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/system-logs/frontend-error",
                json={
                    "summary": "Uncaught TypeError",
                    "detail": "Cannot read property 'x' of null",
                    "module": "Dashboard.vue",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok"}

        # write_log should have been called with level=ERROR, source=frontend
        mock_write_log.assert_awaited_once()
        call_kwargs = mock_write_log.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert call_kwargs["source"] == "frontend"
        assert call_kwargs["summary"] == "Uncaught TypeError"
        assert call_kwargs["user_id"] == 5
        assert call_kwargs["username"] == "guest1"

    @pytest.mark.asyncio
    async def test_report_error_no_auth(self):
        """Without auth override, the endpoint should return 401 (no credentials)."""
        app = _create_app()  # no overrides
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/system-logs/frontend-error",
                json={"summary": "error"},
            )

        # HTTPBearer returns 401 when no Authorization header is present
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# TestGetLogs
# ══════════════════════════════════════════════════════════════════


class TestGetLogs:
    """Tests for GET /system-logs (root only, paginated)."""

    @pytest.mark.asyncio
    async def test_get_logs_basic(self, root_user):
        """Root user gets paginated log items."""
        session = _make_mock_session()

        log1 = _make_log_row(id=1, level="ERROR", source="api", summary="err1")
        log2 = _make_log_row(id=2, level="INFO", source="service", summary="info1")

        # First execute: count query -> returns scalar 2
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # Second execute: select query -> returns scalars list
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [log1, log2]

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["page"] == 1
        assert body["page_size"] == 50
        assert len(body["items"]) == 2
        assert body["items"][0]["id"] == 1
        assert body["items"][0]["level"] == "ERROR"
        assert body["items"][1]["id"] == 2

    @pytest.mark.asyncio
    async def test_get_logs_with_filters(self, root_user):
        """Passing level and source filters still returns 200.
        Verifying that filtering query parameters are accepted."""
        session = _make_mock_session()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        log1 = _make_log_row(id=10, level="ERROR", source="api", summary="filtered")
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [log1]

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/system-logs",
                params={"level": "ERROR", "source": "api"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["level"] == "ERROR"
        assert body["items"][0]["source"] == "api"

    @pytest.mark.asyncio
    async def test_get_logs_pagination(self, root_user):
        """page=2, page_size=10 should be accepted and reflected in response."""
        session = _make_mock_session()

        count_result = MagicMock()
        count_result.scalar.return_value = 25

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [
            _make_log_row(id=i) for i in range(11, 21)
        ]

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/system-logs",
                params={"page": 2, "page_size": 10},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["page_size"] == 10
        assert body["total"] == 25
        assert body["total_pages"] == 3  # ceil(25/10)
        assert len(body["items"]) == 10

    @pytest.mark.asyncio
    async def test_get_logs_non_root_rejected(self, pm_user):
        """PM user should be rejected from the root-only endpoint with 403."""
        from app.api.endpoints.auth import require_root as _real_require_root

        app = FastAPI()
        app.include_router(router)
        # Override get_current_user to return PM payload
        app.dependency_overrides[get_current_user] = lambda: pm_user
        # Do NOT override require_root -- let it check the role naturally.
        # But since require_root depends on get_current_user which is already
        # overridden, it will get the PM payload and should raise 403.

        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_logs_with_search(self, root_user):
        """Search parameter should be accepted and response is 200."""
        session = _make_mock_session()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        log1 = _make_log_row(id=99, summary="keyword match")
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [log1]

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/system-logs",
                params={"search": "keyword"},
            )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_get_logs_with_date_range(self, root_user):
        """start_date and end_date query params should be accepted."""
        session = _make_mock_session()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/system-logs",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["total_pages"] == 0

    @pytest.mark.asyncio
    async def test_get_logs_empty(self, root_user):
        """When there are no logs, total=0, items=[], total_pages=0."""
        session = _make_mock_session()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_result, rows_result])

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["total_pages"] == 0


# ══════════════════════════════════════════════════════════════════
# TestGetStats
# ══════════════════════════════════════════════════════════════════


class TestGetStats:
    """Tests for GET /system-logs/stats."""

    @pytest.mark.asyncio
    async def test_get_stats(self, root_user):
        """Mock session returning level counts produces correct stats."""
        session = _make_mock_session()

        # The endpoint does: result.all() which returns rows with .level and .count
        row_error = MagicMock()
        row_error.level = "ERROR"
        row_error.count = 5

        row_warning = MagicMock()
        row_warning.level = "WARNING"
        row_warning.count = 12

        row_info = MagicMock()
        row_info.level = "INFO"
        row_info.count = 100

        stats_result = MagicMock()
        stats_result.all.return_value = [row_error, row_warning, row_info]

        session.execute = AsyncMock(return_value=stats_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == 5
        assert body["warning"] == 12
        assert body["info"] == 100
        assert body["total"] == 117

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, root_user):
        """When no log rows exist, all counts should be 0."""
        session = _make_mock_session()

        stats_result = MagicMock()
        stats_result.all.return_value = []

        session.execute = AsyncMock(return_value=stats_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == 0
        assert body["warning"] == 0
        assert body["info"] == 0
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_non_root_rejected(self, pm_user):
        """PM user should be rejected from stats endpoint."""
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: pm_user

        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/system-logs/stats")

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# TestCleanup
# ══════════════════════════════════════════════════════════════════


class TestCleanup:
    """Tests for DELETE /system-logs/cleanup."""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.system_logs.write_log", new_callable=AsyncMock)
    async def test_cleanup_success(self, mock_write_log, root_user):
        """Default retain_days=30 cleanup returns deleted_count."""
        session = _make_mock_session()

        delete_result = MagicMock()
        delete_result.rowcount = 42

        session.execute = AsyncMock(return_value=delete_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/system-logs/cleanup")

        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 42
        assert body["retain_days"] == 30

        # commit should have been called
        session.commit.assert_awaited_once()

        # write_log should have been called to record the cleanup
        mock_write_log.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.api.endpoints.system_logs.write_log", new_callable=AsyncMock)
    async def test_cleanup_custom_retain(self, mock_write_log, root_user):
        """retain_days=7 should be accepted and reflected in response."""
        session = _make_mock_session()

        delete_result = MagicMock()
        delete_result.rowcount = 100

        session.execute = AsyncMock(return_value=delete_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(
                "/system-logs/cleanup",
                params={"retain_days": 7},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 100
        assert body["retain_days"] == 7

    @pytest.mark.asyncio
    @patch("app.api.endpoints.system_logs.write_log", new_callable=AsyncMock)
    async def test_cleanup_zero_deleted(self, mock_write_log, root_user):
        """When no logs are old enough, deleted_count should be 0."""
        session = _make_mock_session()

        delete_result = MagicMock()
        delete_result.rowcount = 0

        session.execute = AsyncMock(return_value=delete_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/system-logs/cleanup")

        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_non_root_rejected(self, pm_user):
        """PM user should be rejected from cleanup endpoint."""
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: pm_user

        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/system-logs/cleanup")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("app.api.endpoints.system_logs.write_log", new_callable=AsyncMock)
    async def test_cleanup_retain_days_365(self, mock_write_log, root_user):
        """Maximum retain_days=365 should be accepted."""
        session = _make_mock_session()

        delete_result = MagicMock()
        delete_result.rowcount = 5

        session.execute = AsyncMock(return_value=delete_result)

        app = _create_app(user_override=root_user, session_override=session)
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(
                "/system-logs/cleanup",
                params={"retain_days": 365},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["retain_days"] == 365
