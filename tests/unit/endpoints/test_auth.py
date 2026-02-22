"""
Tests for app.api.endpoints.auth — Auth API endpoints.

Uses httpx.AsyncClient + ASGITransport to test the FastAPI router directly.
AuthService methods are mocked with unittest.mock.patch so no real DB is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import (
    check_maintenance_access,
    get_current_user,
    require_root,
    require_write,
    router,
)
from app.core.enums import UserRole


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _create_test_app(user_override=None):
    """Build a minimal FastAPI app that includes the auth router.

    Note: router already defines prefix="/auth", so we do NOT pass prefix again.
    """
    app = FastAPI()
    app.include_router(router)
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
    return app


def _make_user_mock(
    *,
    id: int = 1,
    username: str = "testuser",
    display_name: str = "Test User",
    role: UserRole = UserRole.ROOT,
    email: str | None = "test@example.com",
    maintenance_id: str | None = None,
    is_active: bool = True,
    last_login_at=None,
):
    """Create a MagicMock that behaves like a User ORM instance."""
    user = MagicMock()
    user.id = id
    user.username = username
    user.display_name = display_name
    user.role = role
    user.email = email
    user.maintenance_id = maintenance_id
    user.is_active = is_active
    user.last_login_at = last_login_at
    return user


# ══════════════════════════════════════════════════════════════════
# TestLogin
# ══════════════════════════════════════════════════════════════════


class TestLogin:
    """Tests for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self):
        """Successful authentication returns 200 with token and user data."""
        mock_user = _make_user_mock(
            id=1,
            username="root",
            display_name="Admin",
            role=UserRole.ROOT,
            email="root@example.com",
            maintenance_id=None,
        )
        mock_token = "jwt-token-abc"

        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.authenticate",
            new_callable=AsyncMock,
            return_value=(mock_user, mock_token, None),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/auth/login",
                    json={"username": "root", "password": "admin123"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["token"] == "jwt-token-abc"
        assert body["user"]["id"] == 1
        assert body["user"]["username"] == "root"
        assert body["user"]["role"] == "ROOT"
        assert body["user"]["is_root"] is True

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """Wrong password returns 401 with error detail."""
        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.authenticate",
            new_callable=AsyncMock,
            return_value=(None, None, "帳號或密碼錯誤"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/auth/login",
                    json={"username": "root", "password": "wrong"},
                )

        assert resp.status_code == 401
        assert "帳號或密碼錯誤" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_inactive_user(self):
        """Inactive user returns 401 with activation message."""
        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.authenticate",
            new_callable=AsyncMock,
            return_value=(None, None, "帳號尚未啟用"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/auth/login",
                    json={"username": "guest1", "password": "pass"},
                )

        assert resp.status_code == 401
        assert "帳號尚未啟用" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestGetMe
# ══════════════════════════════════════════════════════════════════


class TestGetMe:
    """Tests for GET /auth/me."""

    @pytest.mark.asyncio
    async def test_get_me_success(self):
        """Authenticated user gets their own profile data."""
        user_payload = {
            "user_id": 1,
            "username": "root",
            "role": "ROOT",
            "maintenance_id": None,
            "display_name": "Admin",
            "is_root": True,
        }
        db_user = _make_user_mock(
            id=1,
            username="root",
            display_name="Admin",
            role=UserRole.ROOT,
            email="root@example.com",
            maintenance_id=None,
        )

        app = _create_test_app(user_override=user_payload)
        with patch(
            "app.api.endpoints.auth.AuthService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=db_user,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/auth/me")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["username"] == "root"
        assert body["role"] == "ROOT"
        assert body["is_root"] is True
        assert body["email"] == "root@example.com"

    @pytest.mark.asyncio
    async def test_get_me_user_not_found(self):
        """If the user no longer exists in DB, return 404."""
        user_payload = {
            "user_id": 999,
            "username": "deleted",
            "role": "PM",
            "maintenance_id": "MAINT-001",
            "display_name": "Deleted User",
            "is_root": False,
        }

        app = _create_test_app(user_override=user_payload)
        with patch(
            "app.api.endpoints.auth.AuthService.get_user_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/auth/me")

        assert resp.status_code == 404
        assert "使用者不存在" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestChangePassword
# ══════════════════════════════════════════════════════════════════


class TestChangePassword:
    """Tests for PUT /auth/change-password."""

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        """Correct old password returns 200 with success message."""
        user_payload = {
            "user_id": 1,
            "username": "root",
            "role": "ROOT",
            "maintenance_id": None,
            "display_name": "Admin",
            "is_root": True,
        }

        app = _create_test_app(user_override=user_payload)
        with patch(
            "app.api.endpoints.auth.AuthService.change_password",
            new_callable=AsyncMock,
            return_value=True,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.put(
                    "/auth/change-password",
                    json={"old_password": "admin123", "new_password": "newpass"},
                )

        assert resp.status_code == 200
        assert "密碼變更成功" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_change_password_wrong_old(self):
        """Wrong old password returns 400."""
        user_payload = {
            "user_id": 1,
            "username": "root",
            "role": "ROOT",
            "maintenance_id": None,
            "display_name": "Admin",
            "is_root": True,
        }

        app = _create_test_app(user_override=user_payload)
        with patch(
            "app.api.endpoints.auth.AuthService.change_password",
            new_callable=AsyncMock,
            return_value=False,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.put(
                    "/auth/change-password",
                    json={"old_password": "wrong", "new_password": "newpass"},
                )

        assert resp.status_code == 400
        assert "舊密碼錯誤" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestRegisterGuest
# ══════════════════════════════════════════════════════════════════


class TestRegisterGuest:
    """Tests for POST /auth/register-guest."""

    @pytest.mark.asyncio
    async def test_register_success(self):
        """Successful registration returns 200 with username and maintenance_id."""
        mock_user = _make_user_mock(
            id=10,
            username="newguest",
            display_name="New Guest",
            role=UserRole.GUEST,
            maintenance_id="MAINT-001",
            is_active=False,
        )

        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.register_guest",
            new_callable=AsyncMock,
            return_value=(mock_user, None),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/auth/register-guest",
                    json={
                        "username": "newguest",
                        "password": "pass123",
                        "maintenance_id": "MAINT-001",
                        "display_name": "New Guest",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "newguest"
        assert body["maintenance_id"] == "MAINT-001"
        assert "註冊成功" in body["message"]

    @pytest.mark.asyncio
    async def test_register_duplicate(self):
        """Duplicate username returns 400."""
        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.register_guest",
            new_callable=AsyncMock,
            return_value=(None, "使用者名稱已存在"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/auth/register-guest",
                    json={
                        "username": "existing",
                        "password": "pass",
                        "maintenance_id": "MAINT-001",
                    },
                )

        assert resp.status_code == 400
        assert "使用者名稱已存在" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestInitRoot
# ══════════════════════════════════════════════════════════════════


class TestInitRoot:
    """Tests for POST /auth/init-root."""

    @pytest.mark.asyncio
    async def test_init_root_success(self):
        """When root does not exist yet, create it and return 200."""
        mock_root = _make_user_mock(
            id=1,
            username="root",
            display_name="系統管理員",
            role=UserRole.ROOT,
        )

        app = _create_test_app()
        with patch(
            "app.api.endpoints.auth.AuthService.create_root_if_not_exists",
            new_callable=AsyncMock,
            return_value=mock_root,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post("/auth/init-root")

        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "root"
        assert "Root 帳號已就緒" in body["message"]


# ══════════════════════════════════════════════════════════════════
# TestListMaintenancesPublic
# ══════════════════════════════════════════════════════════════════


class TestListMaintenancesPublic:
    """Tests for GET /auth/maintenances-public."""

    @pytest.mark.asyncio
    async def test_list_public(self):
        """Returns list of maintenance configs with id and name."""
        # Build mock MaintenanceConfig rows
        mc1 = MagicMock()
        mc1.maintenance_id = "MAINT-001"
        mc1.name = "First Maintenance"

        mc2 = MagicMock()
        mc2.maintenance_id = "MAINT-002"
        mc2.name = None  # name is None, should fallback to maintenance_id

        # Mock the session dependency
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mc1, mc2]
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.db.base import get_async_session

        app = _create_test_app()
        app.dependency_overrides[get_async_session] = lambda: mock_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/auth/maintenances-public")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["id"] == "MAINT-001"
        assert body[0]["name"] == "First Maintenance"
        assert body[1]["id"] == "MAINT-002"
        assert body[1]["name"] == "MAINT-002"  # fallback when name is None


# ══════════════════════════════════════════════════════════════════
# TestAuthDependencies
# ══════════════════════════════════════════════════════════════════


class TestAuthDependencies:
    """Tests for the authorization dependency helpers."""

    @pytest.mark.asyncio
    async def test_require_write_blocks_guest(self):
        """GUEST role cannot access write-protected endpoints (403)."""
        guest_payload = {
            "user_id": 3,
            "username": "guest1",
            "role": "GUEST",
            "maintenance_id": "MAINT-001",
            "display_name": "Guest User",
            "is_root": False,
        }

        # Build a mini app with a write-protected endpoint
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: guest_payload

        # The change-password endpoint depends on get_current_user but not
        # require_write.  We need an endpoint that uses require_write().
        # Let's add a small test route that uses the dependency.
        from fastapi import Depends

        @app.put("/test-write", dependencies=[Depends(require_write())])
        async def _test_write():
            return {"ok": True}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.put("/test-write")

        assert resp.status_code == 403
        assert "寫入權限" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_require_root_blocks_pm(self):
        """PM role cannot access root-only endpoints (403)."""
        pm_payload = {
            "user_id": 2,
            "username": "pm1",
            "role": "PM",
            "maintenance_id": "MAINT-001",
            "display_name": "PM User",
            "is_root": False,
        }

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: pm_payload

        from fastapi import Depends

        @app.get("/test-root", dependencies=[Depends(require_root)])
        async def _test_root():
            return {"ok": True}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/test-root")

        assert resp.status_code == 403
        assert "管理員權限" in resp.json()["detail"]

    def test_check_maintenance_access_cross(self):
        """PM user accessing a different maintenance raises 403."""
        pm_payload = {
            "user_id": 2,
            "username": "pm1",
            "role": "PM",
            "maintenance_id": "MAINT-001",
            "display_name": "PM User",
            "is_root": False,
        }

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            check_maintenance_access(pm_payload, "MAINT-999")

        assert exc_info.value.status_code == 403
        assert "權限" in exc_info.value.detail

    def test_check_maintenance_access_root_passes(self):
        """ROOT user can access any maintenance without raising."""
        root_payload = {
            "user_id": 1,
            "username": "root",
            "role": "ROOT",
            "maintenance_id": None,
            "display_name": "Admin",
            "is_root": True,
        }

        # Should not raise
        check_maintenance_access(root_payload, "MAINT-001")
        check_maintenance_access(root_payload, "MAINT-999")
        check_maintenance_access(root_payload, "ANY-ID")

    def test_check_maintenance_access_same_maintenance_passes(self):
        """PM user accessing their own maintenance does not raise."""
        pm_payload = {
            "user_id": 2,
            "username": "pm1",
            "role": "PM",
            "maintenance_id": "MAINT-001",
            "display_name": "PM User",
            "is_root": False,
        }

        # Should not raise
        check_maintenance_access(pm_payload, "MAINT-001")

    @pytest.mark.asyncio
    async def test_require_write_allows_pm(self):
        """PM role can access write-protected endpoints (200)."""
        pm_payload = {
            "user_id": 2,
            "username": "pm1",
            "role": "PM",
            "maintenance_id": "MAINT-001",
            "display_name": "PM User",
            "is_root": False,
        }

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: pm_payload

        from fastapi import Depends

        @app.put("/test-write", dependencies=[Depends(require_write())])
        async def _test_write():
            return {"ok": True}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.put("/test-write")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_require_write_allows_root(self):
        """ROOT role can access write-protected endpoints (200)."""
        root_payload = {
            "user_id": 1,
            "username": "root",
            "role": "ROOT",
            "maintenance_id": None,
            "display_name": "Admin",
            "is_root": True,
        }

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: root_payload

        from fastapi import Depends

        @app.put("/test-write", dependencies=[Depends(require_write())])
        async def _test_write():
            return {"ok": True}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.put("/test-write")

        assert resp.status_code == 200
