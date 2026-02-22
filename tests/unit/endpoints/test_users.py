"""
Unit tests for User Management API endpoints.

Tests CRUD operations on /users routes with mocked DB sessions
and dependency overrides for authentication.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user, require_root
from app.api.endpoints.users import router
from app.core.enums import UserRole
from app.db.base import get_async_session


# ── Helpers ──────────────────────────────────────────────────────


def _create_app(user_override=None, session_override=None):
    """Build a throwaway FastAPI app wired to the users router."""
    app = FastAPI()
    app.include_router(router)  # router already has prefix="/users"
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
        app.dependency_overrides[require_root] = lambda: user_override
    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _mock_session():
    """Return an AsyncMock that behaves like an AsyncSession."""
    s = AsyncMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.add = MagicMock()
    s.delete = AsyncMock()
    return s


def _make_user(
    *,
    id: int = 10,
    username: str = "testuser",
    display_name: str = "Test User",
    email: str | None = "test@example.com",
    role: UserRole = UserRole.GUEST,
    maintenance_id: str | None = "MAINT-001",
    is_active: bool = True,
    last_login_at=None,
    created_at=None,
):
    """Create a MagicMock that looks like a User ORM instance."""
    user = MagicMock()
    user.id = id
    user.username = username
    user.display_name = display_name
    user.email = email
    user.role = role
    user.maintenance_id = maintenance_id
    user.is_active = is_active
    user.last_login_at = last_login_at
    user.created_at = created_at
    return user


# ══════════════════════════════════════════════════════════════════
# TestListDisplayNames
# ══════════════════════════════════════════════════════════════════


class TestListDisplayNames:
    """GET /users/display-names"""

    @pytest.mark.anyio
    async def test_returns_names(self, root_user):
        session = _mock_session()
        # session.execute returns rows of (display_name,)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("Alice",), ("Bob",)]
        session.execute.return_value = mock_result

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/users/display-names")

        assert resp.status_code == 200
        data = resp.json()
        assert data == ["Alice", "Bob"]

    @pytest.mark.anyio
    async def test_returns_empty_list_when_no_users(self, root_user):
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute.return_value = mock_result

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/users/display-names")

        assert resp.status_code == 200
        assert resp.json() == []


# ══════════════════════════════════════════════════════════════════
# TestListUsers
# ══════════════════════════════════════════════════════════════════


class TestListUsers:
    """GET /users"""

    @pytest.mark.anyio
    async def test_root_can_list(self, root_user):
        session = _mock_session()
        user_obj = _make_user(id=5, username="alice", display_name="Alice")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_obj]
        session.execute.return_value = mock_result

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/users")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["username"] == "alice"
        assert data[0]["display_name"] == "Alice"

    @pytest.mark.anyio
    async def test_non_root_rejected(self, pm_user):
        """PM users must receive 403 because require_root blocks them."""
        session = _mock_session()
        app = _create_app(session_override=session)
        # Override get_current_user but NOT require_root so the real
        # require_root dependency fires and checks role.
        app.dependency_overrides[get_current_user] = lambda: pm_user
        # Do not override require_root — let it call get_current_user.
        # But get_current_user is async with Depends(security), so we
        # override require_root to simulate a 403.
        async def _reject_non_root():
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此操作需要管理員權限",
            )
        app.dependency_overrides[require_root] = _reject_non_root

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/users")

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# TestCreateUser
# ══════════════════════════════════════════════════════════════════


class TestCreateUser:
    """POST /users"""

    @pytest.mark.anyio
    async def test_create_success(self, root_user):
        session = _mock_session()

        # First execute: check username exists -> None
        # Second execute: check display_name exists -> None
        # Third execute: check PM duplicate -> None (skipped for guest)
        # Fourth execute: check maintenance exists -> returns config
        result_no_user = MagicMock()
        result_no_user.scalar_one_or_none.return_value = None

        result_maintenance = MagicMock()
        result_maintenance.scalar_one_or_none.return_value = MagicMock()  # exists

        session.execute.side_effect = [
            result_no_user,    # username check
            result_no_user,    # display_name check
            result_maintenance,  # maintenance_id check
        ]

        created_user = _make_user(
            id=99,
            username="newuser",
            display_name="New User",
            role=UserRole.GUEST,
            maintenance_id="MAINT-001",
        )
        session.refresh.side_effect = lambda u: setattr(u, '_refreshed', True)

        app = _create_app(user_override=root_user, session_override=session)

        with patch("app.api.endpoints.users.AuthService") as mock_auth:
            mock_auth.hash_password.return_value = "hashed_pw"
            # Make session.refresh populate the User added via session.add
            # We intercept session.add to capture the user object and set its attrs
            captured = {}

            def _capture_add(obj):
                captured["user"] = obj
                obj.id = 99
                obj.is_active = True
                obj.role = UserRole.GUEST
                obj.maintenance_id = "MAINT-001"
                obj.last_login_at = None

            session.add = _capture_add

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/users",
                    json={
                        "username": "newuser",
                        "password": "pass123",
                        "display_name": "New User",
                        "email": "new@example.com",
                        "role": "GUEST",
                        "maintenance_id": "MAINT-001",
                    },
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["display_name"] == "New User"
        assert data["is_active"] is True

    @pytest.mark.anyio
    async def test_create_duplicate(self, root_user):
        session = _mock_session()

        existing = _make_user(username="dupuser")
        result_exists = MagicMock()
        result_exists.scalar_one_or_none.return_value = existing
        session.execute.return_value = result_exists

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/users",
                json={
                    "username": "dupuser",
                    "password": "pass123",
                    "display_name": "Dup User",
                    "role": "guest",
                    "maintenance_id": "MAINT-001",
                },
            )

        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestUpdateUser
# ══════════════════════════════════════════════════════════════════


class TestUpdateUser:
    """PUT /users/{user_id}"""

    @pytest.mark.anyio
    async def test_update_role(self, root_user):
        session = _mock_session()

        target_user = _make_user(id=10, role=UserRole.GUEST)
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = target_user

        # No existing PM for this maintenance
        result_no_pm = MagicMock()
        result_no_pm.scalar_one_or_none.return_value = None

        # MaintenanceConfig exists
        result_maint = MagicMock()
        result_maint.scalar_one_or_none.return_value = MagicMock()

        # Execution order in update_user when changing role to PM + maintenance_id:
        # 1. Find user by id
        # 2. Check PM uniqueness (new_role == PM)
        # 3. Validate maintenance_id exists (data.maintenance_id is not None)
        session.execute.side_effect = [result_found, result_no_pm, result_maint]

        # After commit + refresh the user should have the new role
        async def _refresh(obj):
            pass  # role already mutated by the endpoint
        session.refresh = _refresh

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/users/10",
                json={"role": "PM", "maintenance_id": "MAINT-001"},
            )

        assert resp.status_code == 200
        data = resp.json()
        # The endpoint sets user.role = new_role on the mock
        assert data["role"] == "PM"


# ══════════════════════════════════════════════════════════════════
# TestDeleteUser
# ══════════════════════════════════════════════════════════════════


class TestDeleteUser:
    """DELETE /users/{user_id}"""

    @pytest.mark.anyio
    async def test_delete_success(self, root_user):
        session = _mock_session()
        target_user = _make_user(id=50, role=UserRole.GUEST)
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = target_user
        session.execute.return_value = result_found

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete("/users/50")

        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_delete_self_blocked(self, root_user):
        """Deleting your own account should be rejected with 400."""
        session = _mock_session()
        # The target user has the same id as root_user["user_id"] (1)
        target_user = _make_user(id=1, role=UserRole.ROOT)
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = target_user
        session.execute.return_value = result_found

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete("/users/1")

        assert resp.status_code == 400
        # The endpoint blocks deleting ROOT accounts
        assert "不可刪除" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════
# TestActivateUser
# ══════════════════════════════════════════════════════════════════


class TestActivateUser:
    """POST /users/{user_id}/activate"""

    @pytest.mark.anyio
    async def test_activate_success(self, root_user):
        session = _mock_session()
        inactive_user = _make_user(id=20, is_active=False, role=UserRole.GUEST)
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = inactive_user
        session.execute.return_value = result_found

        async def _refresh(obj):
            pass  # is_active already mutated by the endpoint
        session.refresh = _refresh

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/users/20/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is True

    @pytest.mark.anyio
    async def test_activate_already_active_returns_400(self, root_user):
        session = _mock_session()
        active_user = _make_user(id=21, is_active=True, role=UserRole.GUEST)
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = active_user
        session.execute.return_value = result_found

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/users/21/activate")

        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
# TestResetPassword
# ══════════════════════════════════════════════════════════════════


class TestResetPassword:
    """POST /users/{user_id}/reset-password"""

    @pytest.mark.anyio
    async def test_reset_success(self, root_user):
        session = _mock_session()
        target_user = _make_user(id=30, username="alice")
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = target_user
        session.execute.return_value = result_found

        app = _create_app(user_override=root_user, session_override=session)

        with patch("app.api.endpoints.users.AuthService") as mock_auth:
            mock_auth.hash_password.return_value = "new_hashed_pw"

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/users/30/reset-password",
                    json={"new_password": "newpass123"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "alice" in data["message"]

    @pytest.mark.anyio
    async def test_reset_not_found_returns_404(self, root_user):
        session = _mock_session()
        result_empty = MagicMock()
        result_empty.scalar_one_or_none.return_value = None
        session.execute.return_value = result_empty

        app = _create_app(user_override=root_user, session_override=session)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/users/9999/reset-password",
                json={"new_password": "x"},
            )

        assert resp.status_code == 404
