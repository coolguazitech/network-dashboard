"""
Repository package.

Provides data access layer using Repository Pattern.
"""
from app.repositories.base import BaseRepository
from app.repositories.indicator_result import IndicatorResultRepository
from app.repositories.typed_records import (
    TypedRecordRepository,
    get_typed_repo,
)

__all__ = [
    "BaseRepository",
    "IndicatorResultRepository",
    "TypedRecordRepository",
    "get_typed_repo",
]
