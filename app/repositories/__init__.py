"""
Repository package.

Provides data access layer using Repository Pattern.
"""
from app.repositories.base import BaseRepository
from app.repositories.collection_record import CollectionRecordRepository
from app.repositories.indicator_result import IndicatorResultRepository
from app.repositories.switch import SwitchRepository

__all__ = [
    "BaseRepository",
    "SwitchRepository",
    "CollectionRecordRepository",
    "IndicatorResultRepository",
]
