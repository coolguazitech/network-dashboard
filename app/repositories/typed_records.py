"""
Typed Record Repositories.

Data access layer for typed record tables.
Each typed repo handles one scheduler API's records.

TYPED_REPO_MAP key = scheduler.yaml API name = CollectionBatch.collection_type
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import (
    CollectionBatch,
    DynamicAclRecord,
    FanRecord,
    InterfaceErrorRecord,
    InterfaceStatusRecord,
    LatestCollectionBatch,
    MacTableRecord,
    NeighborRecord,
    PingRecord,
    PortChannelRecord,
    PowerRecord,
    StaticAclRecord,
    TransceiverRecord,
    VersionRecord,
)

RecordT = TypeVar("RecordT", bound=Base)


def _compute_hash(parsed_items: list[BaseModel]) -> str:
    """計算 parsed items 的確定性 hash（16 hex chars）。"""
    data = sorted(
        [item.model_dump(mode="json") for item in parsed_items],
        key=lambda x: json.dumps(x, sort_keys=True),
    )
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


class TypedRecordRepository(Generic[RecordT]):
    """
    Generic repository for typed record tables.

    Provides common query patterns shared by all collection types:
    - save_batch: create CollectionBatch + typed rows
    - get_latest_per_device: latest batch of rows per hostname
    - get_time_series_records: typed rows ordered by time
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
        maintenance_id: str,
    ) -> CollectionBatch | None:
        """
        Save a collection batch + typed rows (基準 + 變化點策略).

        比對 data_hash：
        - 首次採集 → 建 batch + typed rows + LatestCollectionBatch
        - hash 相同 → 只更新 last_checked_at，不建新 batch
        - hash 不同 → 資料有變化，建新 batch + typed rows + 更新指標

        Returns:
            The created CollectionBatch, or None if skipped (unchanged).
        """
        now = datetime.now(UTC)
        data_hash = _compute_hash(parsed_items)

        # 查找現有指標
        stmt = select(LatestCollectionBatch).where(
            LatestCollectionBatch.maintenance_id == maintenance_id,
            LatestCollectionBatch.collection_type == self.collection_type,
            LatestCollectionBatch.switch_hostname == switch_hostname,
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()

        if latest and latest.data_hash == data_hash:
            # 資料未變化 → 只更新 last_checked_at
            latest.last_checked_at = now
            await self.session.flush()
            return None

        # 資料有變化（或首次採集）→ 建新 batch
        batch = CollectionBatch(
            collection_type=self.collection_type,
            switch_hostname=switch_hostname,
            maintenance_id=maintenance_id,
            raw_data=raw_data,
            item_count=len(parsed_items),
            collected_at=now,
        )
        self.session.add(batch)
        await self.session.flush()  # get batch.id

        # 建 typed rows
        for item in parsed_items:
            row = self.model(
                batch_id=batch.id,
                switch_hostname=switch_hostname,
                maintenance_id=maintenance_id,
                collected_at=now,
                **item.model_dump(),
            )
            self.session.add(row)

        # 更新或建立 LatestCollectionBatch 指標
        if latest:
            latest.batch_id = batch.id
            latest.data_hash = data_hash
            latest.collected_at = now
            latest.last_checked_at = now
        else:
            self.session.add(LatestCollectionBatch(
                maintenance_id=maintenance_id,
                collection_type=self.collection_type,
                switch_hostname=switch_hostname,
                batch_id=batch.id,
                data_hash=data_hash,
                collected_at=now,
                last_checked_at=now,
            ))

        await self.session.flush()
        return batch

    async def get_latest_per_device(
        self,
        maintenance_id: str,
    ) -> list[RecordT]:
        """
        Get the latest batch of typed rows per device.

        Uses LatestCollectionBatch for O(1) lookup of latest batch_id,
        then JOINs to get all typed rows from those batches.
        """
        latest = (
            select(LatestCollectionBatch.batch_id)
            .where(
                LatestCollectionBatch.collection_type == self.collection_type,
                LatestCollectionBatch.maintenance_id == maintenance_id,
            )
            .subquery()
        )

        stmt = select(self.model).where(
            self.model.batch_id.in_(select(latest.c.batch_id)),
            self.model.maintenance_id == maintenance_id,
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_batch_info(
        self,
        maintenance_id: str,
    ) -> list[LatestCollectionBatch]:
        """查所有設備的最新狀態摘要。"""
        stmt = select(LatestCollectionBatch).where(
            LatestCollectionBatch.collection_type == self.collection_type,
            LatestCollectionBatch.maintenance_id == maintenance_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_change_history(
        self,
        maintenance_id: str,
        switch_hostname: str,
    ) -> list[CollectionBatch]:
        """查某設備的所有變化點。"""
        stmt = (
            select(CollectionBatch)
            .where(
                CollectionBatch.collection_type == self.collection_type,
                CollectionBatch.maintenance_id == maintenance_id,
                CollectionBatch.switch_hostname == switch_hostname,
            )
            .order_by(CollectionBatch.collected_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_changes_summary(
        self,
        maintenance_id: str,
    ) -> list[dict[str, Any]]:
        """查整個歲修中哪些設備有過變化、變了幾次。"""
        stmt = (
            select(
                CollectionBatch.switch_hostname,
                func.count().label("change_count"),
                func.min(CollectionBatch.collected_at).label("first_change"),
                func.max(CollectionBatch.collected_at).label("last_change"),
            )
            .where(
                CollectionBatch.collection_type == self.collection_type,
                CollectionBatch.maintenance_id == maintenance_id,
            )
            .group_by(CollectionBatch.switch_hostname)
            .order_by(func.max(CollectionBatch.collected_at).desc())
        )
        result = await self.session.execute(stmt)
        return [
            {
                "switch_hostname": row.switch_hostname,
                "change_count": row.change_count,
                "first_change": row.first_change,
                "last_change": row.last_change,
            }
            for row in result.fetchall()
        ]

    async def get_time_series_records(
        self,
        maintenance_id: str,
        limit: int = 100,
    ) -> list[RecordT]:
        """Get typed rows ordered by collected_at desc, with limit."""
        stmt = (
            select(self.model)
            .where(self.model.maintenance_id == maintenance_id)
            .order_by(self.model.collected_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_records(
        self,
        maintenance_id: str,
        limit: int = 100,
    ) -> list[RecordT]:
        """Get latest typed rows (for raw data table display)."""
        stmt = (
            select(self.model)
            .where(self.model.maintenance_id == maintenance_id)
            .order_by(self.model.collected_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ── Concrete Repositories ─────────────────────────────────────


class TransceiverRecordRepo(TypedRecordRepository[TransceiverRecord]):
    model = TransceiverRecord
    collection_type = "get_gbic_details"


class PortChannelRecordRepo(TypedRecordRepository[PortChannelRecord]):
    model = PortChannelRecord
    collection_type = "get_channel_group"


class NeighborRecordRepo(TypedRecordRepository[NeighborRecord]):
    model = NeighborRecord
    collection_type = "get_uplink"


class InterfaceErrorRecordRepo(TypedRecordRepository[InterfaceErrorRecord]):
    model = InterfaceErrorRecord
    collection_type = "get_error_count"


class StaticAclRecordRepo(TypedRecordRepository[StaticAclRecord]):
    model = StaticAclRecord
    collection_type = "get_static_acl"


class DynamicAclRecordRepo(TypedRecordRepository[DynamicAclRecord]):
    model = DynamicAclRecord
    collection_type = "get_dynamic_acl"



class MacTableRecordRepo(TypedRecordRepository[MacTableRecord]):
    model = MacTableRecord
    collection_type = "get_mac_table"


class FanRecordRepo(TypedRecordRepository[FanRecord]):
    model = FanRecord
    collection_type = "get_fan"


class PowerRecordRepo(TypedRecordRepository[PowerRecord]):
    model = PowerRecord
    collection_type = "get_power"


class VersionRecordRepo(TypedRecordRepository[VersionRecord]):
    model = VersionRecord
    collection_type = "get_version"


class PingRecordRepo(TypedRecordRepository[PingRecord]):
    model = PingRecord
    collection_type = "ping_batch"


class InterfaceStatusRecordRepo(TypedRecordRepository[InterfaceStatusRecord]):
    model = InterfaceStatusRecord
    collection_type = "get_interface_status"


class ClientPingRecordRepo(TypedRecordRepository[PingRecord]):
    """Client IP Ping records (gnms_ping)，與 PingRecordRepo 共用 PingRecord model。"""

    model = PingRecord
    collection_type = "gnms_ping"


# ── Factory ──────────────────────────────────────────────────────

TYPED_REPO_MAP: dict[str, type[TypedRecordRepository[Any]]] = {
    "get_gbic_details": TransceiverRecordRepo,
    "get_channel_group": PortChannelRecordRepo,
    "get_uplink": NeighborRecordRepo,
    "get_error_count": InterfaceErrorRecordRepo,
    "get_static_acl": StaticAclRecordRepo,
    "get_dynamic_acl": DynamicAclRecordRepo,
"get_mac_table": MacTableRecordRepo,
    "get_fan": FanRecordRepo,
    "get_power": PowerRecordRepo,
    "get_version": VersionRecordRepo,
    "ping_batch": PingRecordRepo,
    "get_interface_status": InterfaceStatusRecordRepo,
    "gnms_ping": ClientPingRecordRepo,
}


def get_typed_repo(
    collection_type: str,
    session: AsyncSession,
) -> TypedRecordRepository[Any]:
    """
    Factory: get the correct typed repo for a collection type.

    Raises:
        KeyError: if collection_type is not registered
    """
    repo_cls = TYPED_REPO_MAP.get(collection_type)
    if repo_cls is None:
        available = ", ".join(sorted(TYPED_REPO_MAP.keys()))
        raise KeyError(
            f"未註冊的採集類型 '{collection_type}'。"
            f"可用類型: {available}"
        )
    return repo_cls(session)
