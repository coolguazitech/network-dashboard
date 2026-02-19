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
