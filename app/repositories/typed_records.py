"""
Typed Record Repositories.

Data access layer for typed record tables (replacing CollectionRecord's JSON blob).
Each typed repo handles one collection type's records.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase
from app.db.base import Base
from app.db.models import (
    CollectionBatch,
    FanRecord,
    InterfaceErrorRecord,
    NeighborRecord,
    PingRecord,
    PortChannelRecord,
    PowerRecord,
    TransceiverRecord,
    VersionRecord,
)

RecordT = TypeVar("RecordT", bound=Base)


class TypedRecordRepository(Generic[RecordT]):
    """
    Generic repository for typed record tables.

    Provides common query patterns shared by all 8 collection types:
    - save_batch: create CollectionBatch + typed rows
    - get_latest_per_device: latest batch of rows per hostname
    - get_time_series_batches: batches ordered by time
    - get_latest_records: raw typed rows ordered by time
    """

    model: type[RecordT]
    collection_type: str

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_batch(
        self,
        switch_hostname: str,
        raw_data: str,
        parsed_items: list[BaseModel],
        phase: MaintenancePhase,
        maintenance_id: str,
    ) -> CollectionBatch:
        """
        Save a collection batch + typed rows.

        Args:
            switch_hostname: Device hostname
            raw_data: Raw CLI output (kept for debugging)
            parsed_items: Pydantic models from parser
            phase: OLD / NEW
            maintenance_id: Maintenance job ID

        Returns:
            The created CollectionBatch
        """
        now = datetime.utcnow()

        # 1. Create batch header
        batch = CollectionBatch(
            collection_type=self.collection_type,
            switch_hostname=switch_hostname,
            phase=phase,
            maintenance_id=maintenance_id,
            raw_data=raw_data,
            item_count=len(parsed_items),
            collected_at=now,
        )
        self.session.add(batch)
        await self.session.flush()  # get batch.id

        # 2. Create typed rows
        for item in parsed_items:
            row = self.model(
                batch_id=batch.id,
                switch_hostname=switch_hostname,
                phase=phase,
                maintenance_id=maintenance_id,
                collected_at=now,
                **item.model_dump(),
            )
            self.session.add(row)

        await self.session.flush()
        return batch

    async def get_latest_per_device(
        self,
        phase: MaintenancePhase,
        maintenance_id: str,
    ) -> list[RecordT]:
        """
        Get the latest batch of typed rows per device.

        Uses MAX(batch_id) per hostname to find the most recent batch,
        then JOINs to get all typed rows from those batches.
        """
        # Subquery: latest batch_id per hostname
        latest = (
            select(
                CollectionBatch.switch_hostname,
                func.max(CollectionBatch.id).label("max_id"),
            )
            .where(
                CollectionBatch.collection_type == self.collection_type,
                CollectionBatch.phase == phase,
                CollectionBatch.maintenance_id == maintenance_id,
            )
            .group_by(CollectionBatch.switch_hostname)
            .subquery()
        )

        # Main query: typed rows from latest batches
        stmt = select(self.model).join(
            latest,
            and_(
                self.model.switch_hostname == latest.c.switch_hostname,
                self.model.batch_id == latest.c.max_id,
            ),
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_time_series_records(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
        limit: int = 100,
    ) -> list[RecordT]:
        """
        Get typed rows ordered by collected_at desc, with limit.

        Used by indicator get_time_series().
        """
        stmt = (
            select(self.model)
            .where(
                self.model.maintenance_id == maintenance_id,
                self.model.phase == phase,
            )
            .order_by(self.model.collected_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_records(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
        limit: int = 100,
    ) -> list[RecordT]:
        """
        Get latest typed rows (for raw data table display).
        """
        stmt = (
            select(self.model)
            .where(
                self.model.maintenance_id == maintenance_id,
                self.model.phase == phase,
            )
            .order_by(self.model.collected_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ── 8 Concrete Repositories ─────────────────────────────────────


class TransceiverRecordRepo(TypedRecordRepository[TransceiverRecord]):
    model = TransceiverRecord
    collection_type = "transceiver"


class VersionRecordRepo(TypedRecordRepository[VersionRecord]):
    model = VersionRecord
    collection_type = "version"


class NeighborRecordRepo(TypedRecordRepository[NeighborRecord]):
    model = NeighborRecord
    collection_type = "uplink"


class PortChannelRecordRepo(TypedRecordRepository[PortChannelRecord]):
    model = PortChannelRecord
    collection_type = "port_channel"


class PowerRecordRepo(TypedRecordRepository[PowerRecord]):
    model = PowerRecord
    collection_type = "power"


class FanRecordRepo(TypedRecordRepository[FanRecord]):
    model = FanRecord
    collection_type = "fan"


class InterfaceErrorRecordRepo(TypedRecordRepository[InterfaceErrorRecord]):
    model = InterfaceErrorRecord
    collection_type = "error_count"


class PingRecordRepo(TypedRecordRepository[PingRecord]):
    model = PingRecord
    collection_type = "ping"


# ── Factory ──────────────────────────────────────────────────────

TYPED_REPO_MAP: dict[str, type[TypedRecordRepository[Any]]] = {
    "transceiver": TransceiverRecordRepo,
    "version": VersionRecordRepo,
    "uplink": NeighborRecordRepo,
    "port_channel": PortChannelRecordRepo,
    "power": PowerRecordRepo,
    "fan": FanRecordRepo,
    "error_count": InterfaceErrorRecordRepo,
    "ping": PingRecordRepo,
}


def get_typed_repo(
    collection_type: str,
    session: AsyncSession,
) -> TypedRecordRepository[Any]:
    """
    Factory: get the correct typed repo for a collection type.

    Args:
        collection_type: e.g. "transceiver", "version", ...
        session: SQLAlchemy async session

    Raises:
        KeyError: if collection_type is not registered
    """
    repo_cls = TYPED_REPO_MAP[collection_type]
    return repo_cls(session)
