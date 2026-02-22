"""
Unit tests for Contacts API endpoints.

Tests category and contact CRUD operations with mocked DB sessions.
"""
from __future__ import annotations

import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.contacts import router

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


def _build_app(user: dict) -> FastAPI:
    """Build a minimal FastAPI app with auth overrides."""
    app = FastAPI()
    app.include_router(router)

    async def _override_current_user():
        return user

    async def _override_require_write():
        from app.core.enums import UserRole
        role = user.get("role")
        if role not in [UserRole.ROOT.value, UserRole.PM.value]:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您沒有寫入權限",
            )
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    # require_write() returns a new function each call, so we override via
    # the inner dependency it produces. We patch it as a factory below.
    return app


def _override_write(app: FastAPI, user: dict) -> None:
    """Override require_write dependency in the app."""
    from app.core.enums import UserRole

    async def _check_write():
        role = user.get("role")
        if role not in [UserRole.ROOT.value, UserRole.PM.value]:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您沒有寫入權限",
            )
        return user

    # The router endpoints use Depends(require_write()) -- require_write() is
    # called at import time and returns check_write. We need to override the
    # result (the inner function) on a per-endpoint basis. The easiest approach
    # is to patch require_write at module level so it returns our override.
    # Instead, we patch get_current_user and let the real require_write() run.
    pass


def _make_mock_session():
    """Create a mock async session for the context manager."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _mock_session_context(session):
    """Return a mock get_session_context that yields the given session."""
    @asynccontextmanager
    async def _ctx():
        yield session
    return _ctx


# ========== Category Mock Helpers ==========


def _make_category_obj(**kwargs):
    """Create a mock ContactCategory object."""
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.name = kwargs.get("name", "Network")
    obj.description = kwargs.get("description", "Network team")
    obj.color = kwargs.get("color", "#3B82F6")
    obj.icon = kwargs.get("icon", None)
    obj.sort_order = kwargs.get("sort_order", 0)
    obj.is_active = kwargs.get("is_active", True)
    return obj


def _make_contact_obj(**kwargs):
    """Create a mock Contact object."""
    obj = MagicMock()
    obj.id = kwargs.get("id", 1)
    obj.maintenance_id = kwargs.get("maintenance_id", "MAINT-001")
    obj.category_id = kwargs.get("category_id", 1)
    obj.name = kwargs.get("name", "Alice")
    obj.title = kwargs.get("title", "Engineer")
    obj.department = kwargs.get("department", "IT")
    obj.company = kwargs.get("company", "ACME")
    obj.phone = kwargs.get("phone", "02-1234-5678")
    obj.mobile = kwargs.get("mobile", "0912345678")
    obj.email = kwargs.get("email", "alice@example.com")
    obj.extension = kwargs.get("extension", "100")
    obj.notes = kwargs.get("notes", None)
    obj.is_active = kwargs.get("is_active", True)
    obj.sort_order = kwargs.get("sort_order", 0)
    return obj


# ========== TestListContactCategories ==========


class TestListContactCategories:
    """Tests for GET /contacts/categories/{maintenance_id}."""

    @pytest.mark.asyncio
    async def test_list_categories(self):
        """GET returns 200 with category list."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        cat = _make_category_obj(id=1, name="Network")
        mock_result = MagicMock()
        mock_result.all.return_value = [(cat, 5)]
        session.execute.return_value = mock_result

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/contacts/categories/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["name"] == "Network"
        assert data[0]["contact_count"] == 5


# ========== TestCreateCategory ==========


class TestCreateCategory:
    """Tests for POST /contacts/categories."""

    @pytest.mark.asyncio
    async def test_create_success(self):
        """POST with valid data returns 200 with new category."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        # First execute: check duplicate -> None
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        # Second execute: count -> 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        session.execute.side_effect = [dup_result, count_result]

        cat = _make_category_obj(id=10, name="New Cat", sort_order=0)
        session.refresh.side_effect = lambda obj: setattr(obj, "id", 10) or setattr(obj, "sort_order", 0)

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/contacts/categories",
                    json={
                        "maintenance_id": "MAINT-001",
                        "name": "New Cat",
                        "description": "A new category",
                        "color": "#FF0000",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Cat"
        assert data["contact_count"] == 0

    @pytest.mark.asyncio
    async def test_requires_write(self):
        """GUEST user receives 403 Forbidden."""
        app = _build_app(GUEST_USER)
        session = _make_mock_session()

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/contacts/categories",
                    json={
                        "maintenance_id": "MAINT-001",
                        "name": "Test",
                    },
                )

        assert resp.status_code == 403


# ========== TestUpdateCategory ==========


class TestUpdateCategory:
    """Tests for PUT /contacts/categories/{category_id}."""

    @pytest.mark.asyncio
    async def test_update_success(self):
        """PUT returns 200 with updated category."""
        app = _build_app(PM_USER)
        session = _make_mock_session()

        cat = _make_category_obj(id=1, name="Network")

        # First execute: find category
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = cat

        # Second execute: count contacts
        count_result = MagicMock()
        count_result.scalar.return_value = 3

        session.execute.side_effect = [find_result, count_result]

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/contacts/categories/1",
                    json={"name": "Updated Network", "color": "#00FF00"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["contact_count"] == 3


# ========== TestDeleteCategory ==========


class TestDeleteCategory:
    """Tests for DELETE /contacts/categories/{category_id}."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """DELETE returns 200 with confirmation message."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        cat = _make_category_obj(id=1, name="Old Cat")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = cat

        # Second execute: update contacts (set category_id=NULL)
        update_result = MagicMock()

        session.execute.side_effect = [find_result, update_result]

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/contacts/categories/1")

        assert resp.status_code == 200
        data = resp.json()
        assert "Old Cat" in data["message"]


# ========== TestListContacts ==========


class TestListContacts:
    """Tests for GET /contacts/{maintenance_id}."""

    @pytest.mark.asyncio
    async def test_list_success(self):
        """GET returns 200 with contacts."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        contact = _make_contact_obj(id=1, name="Alice")
        mock_result = MagicMock()
        mock_result.all.return_value = [(contact, "Network")]
        session.execute.return_value = mock_result

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/contacts/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Alice"
        assert data[0]["category_name"] == "Network"

    @pytest.mark.asyncio
    async def test_list_with_search(self):
        """GET with search param filters contacts."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        contact = _make_contact_obj(id=2, name="Bob", email="bob@test.com")
        mock_result = MagicMock()
        mock_result.all.return_value = [(contact, "Support")]
        session.execute.return_value = mock_result

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/contacts/MAINT-001", params={"search": "bob"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Bob"


# ========== TestCreateContact ==========


class TestCreateContact:
    """Tests for POST /contacts/{maintenance_id}."""

    @pytest.mark.asyncio
    async def test_create_success(self):
        """POST returns 200 with new contact."""
        app = _build_app(PM_USER)
        session = _make_mock_session()

        # execute for category check
        cat = _make_category_obj(id=1, name="Network")
        cat_result = MagicMock()
        cat_result.scalar_one_or_none.return_value = cat
        session.execute.return_value = cat_result

        # After commit + refresh, contact gets an id
        session.refresh.side_effect = lambda obj: setattr(obj, "id", 42)

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/contacts/MAINT-001",
                    json={
                        "category_id": 1,
                        "name": "Charlie",
                        "phone": "02-9999-0000",
                        "email": "charlie@example.com",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Charlie"
        assert data["category_name"] == "Network"


# ========== TestUpdateContact ==========


class TestUpdateContact:
    """Tests for PUT /contacts/{maintenance_id}/{contact_id}."""

    @pytest.mark.asyncio
    async def test_update_success(self):
        """PUT returns 200 with updated contact."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        contact = _make_contact_obj(id=5, name="Diana", category_id=1)

        # First execute: find contact
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = contact

        # Second execute: get category name
        cat_result = MagicMock()
        cat_result.scalar.return_value = "Network"

        session.execute.side_effect = [find_result, cat_result]

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/contacts/MAINT-001/5",
                    json={"name": "Diana Updated", "phone": "02-1111-2222"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["category_name"] == "Network"


# ========== TestDeleteContact ==========


class TestDeleteContact:
    """Tests for DELETE /contacts/{maintenance_id}/{contact_id}."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """DELETE returns 200 with confirmation message."""
        app = _build_app(ROOT_USER)
        session = _make_mock_session()

        contact = _make_contact_obj(id=3, name="Eve")

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = contact
        session.execute.return_value = find_result

        with patch(
            "app.api.endpoints.contacts.get_session_context",
            _mock_session_context(session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/contacts/MAINT-001/3")

        assert resp.status_code == 200
        data = resp.json()
        assert "Eve" in data["message"]
