"""
Repository package.

Provides data access layer using Repository Pattern.
"""
from app.repositories.typed_records import (
    BaseRepository,
    TypedRecordRepository,
    get_typed_repo,
)

__all__ = [
    "BaseRepository",
    "TypedRecordRepository",
    "get_typed_repo",
]
