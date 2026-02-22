"""Root conftest — shared fixtures for all tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Ensure we use a test database URL (SQLite in-memory) for tests
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+aiosqlite:///file::memory:?cache=shared",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("MOCK_SERVER_URL", "http://localhost:9999")

RAW_DATA_DIR = Path(__file__).parent.parent / "test_data" / "raw"


@pytest.fixture
def raw_data_dir() -> Path:
    """Path to test_data/raw/ directory."""
    return RAW_DATA_DIR


def load_raw(filename: str) -> str:
    """Load a raw test data file by name."""
    path = RAW_DATA_DIR / filename
    if not path.exists():
        pytest.skip(f"Test data file not found: {path}")
    return path.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# Shared user payload fixtures for endpoint tests
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def root_user() -> dict:
    """JWT payload for a ROOT user."""
    return {
        "user_id": 1,
        "username": "root",
        "role": "ROOT",
        "maintenance_id": None,
        "display_name": "系統管理員",
        "is_root": True,
    }


@pytest.fixture
def pm_user() -> dict:
    """JWT payload for a PM user scoped to MAINT-001."""
    return {
        "user_id": 2,
        "username": "pm1",
        "role": "PM",
        "maintenance_id": "MAINT-001",
        "display_name": "PM User",
        "is_root": False,
    }


@pytest.fixture
def guest_user() -> dict:
    """JWT payload for a GUEST user scoped to MAINT-001."""
    return {
        "user_id": 3,
        "username": "guest1",
        "role": "GUEST",
        "maintenance_id": "MAINT-001",
        "display_name": "Guest User",
        "is_root": False,
    }
