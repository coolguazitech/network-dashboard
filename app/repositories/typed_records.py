"""
Typed Record Repositories.

Data access layer for typed record tables.
Each typed repo handles one scheduler API's records.

TYPED_REPO_MAP key = scheduler.yaml API name = CollectionBatch.collection_type
"""

from __future__ import annotations

import hashlib
import json
import re
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

ModelT = TypeVar("ModelT", bound=Base)
RecordT = TypeVar("RecordT", bound=Base)


# ── Base Repository ──────────────────────────────────────────────


class BaseRepository(Generic[ModelT]):
    """Base repository with generic CRUD operations."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: int) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def count(self) -> int:
        from sqlalchemy import func as fn
        stmt = select(fn.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar() or 0


# ── Interface Name Normalization ─────────────────────────────────
# 集中定義在 app.core.interfaces，此處保留 re-export 相容性
from app.core.interfaces import normalize_interface_name  # noqa: F401


# ── Helpers ──────────────────────────────────────────────────────


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

        # 建 typed rows（統一 normalize interface 名稱）
        for item in parsed_items:
            data = item.model_dump()
            if "interface_name" in data and data["interface_name"]:
                data["interface_name"] = normalize_interface_name(
                    data["interface_name"],
                )
            if "local_interface" in data and data["local_interface"]:
                data["local_interface"] = normalize_interface_name(
                    data["local_interface"],
                )
            if "remote_interface" in data and data["remote_interface"]:
                data["remote_interface"] = normalize_interface_name(
                    data["remote_interface"],
                )
            row = self.model(
                batch_id=batch.id,
                switch_hostname=switch_hostname,
                maintenance_id=maintenance_id,
                collected_at=now,
                **data,
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
        offset: int = 0,
    ) -> list[RecordT]:
        """Get latest typed rows (for raw data table display)."""
        stmt = (
            select(self.model)
            .where(self.model.maintenance_id == maintenance_id)
            .order_by(self.model.collected_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_records(self, maintenance_id: str) -> int:
        """Count total records for pagination."""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.maintenance_id == maintenance_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0


# ── Concrete Repositories ─────────────────────────────────────


class _FlatTransceiverItem(BaseModel):
    """TransceiverData 展開後的扁平結構，對應 TransceiverRecord DB 欄位。"""

    interface_name: str
    tx_power: float | None = None
    rx_power: float | None = None
    temperature: float | None = None
    voltage: float | None = None


class TransceiverRecordRepo(TypedRecordRepository[TransceiverRecord]):
    """TransceiverData 為巢狀結構（channels per interface），存 DB 時展開為扁平 rows。"""

    model = TransceiverRecord
    collection_type = "get_gbic_details"

    async def save_batch(
        self,
        switch_hostname: str,
        raw_data: str,
        parsed_items: list[BaseModel],
        maintenance_id: str,
    ) -> CollectionBatch | None:
        """展開 TransceiverData.channels → 每 channel 一筆 TransceiverRecord。"""
        flat_items: list[BaseModel] = []
        for item in parsed_items:
            d = item.model_dump()
            channels = d.pop("channels", [])
            for ch in channels:
                flat_items.append(_FlatTransceiverItem(
                    interface_name=d["interface_name"],
                    temperature=d.get("temperature"),
                    voltage=d.get("voltage"),
                    tx_power=ch.get("tx_power"),
                    rx_power=ch.get("rx_power"),
                ))
        return await super().save_batch(
            switch_hostname, raw_data, flat_items, maintenance_id,
        )


class PortChannelRecordRepo(TypedRecordRepository[PortChannelRecord]):
    model = PortChannelRecord
    collection_type = "get_channel_group"


class NeighborRecordRepo(TypedRecordRepository[NeighborRecord]):
    model = NeighborRecord
    collection_type = "get_uplink"


class NeighborLldpRecordRepo(TypedRecordRepository[NeighborRecord]):
    """LLDP 鄰居記錄（獨立 collection_type，不與 CDP 互相覆蓋）。"""

    model = NeighborRecord
    collection_type = "get_uplink_lldp"


class NeighborCdpRecordRepo(TypedRecordRepository[NeighborRecord]):
    """CDP 鄰居記錄（獨立 collection_type，不與 LLDP 互相覆蓋）。"""

    model = NeighborRecord
    collection_type = "get_uplink_cdp"


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
    """
    Client IP Ping records (gnms_ping)，與 PingRecordRepo 共用 PingRecord model。

    覆寫 save_batch：在既有 batch 上做 in-place 更新，
    只 INSERT/UPDATE 有變化的 record，避免每次寫入全部 client。
    """

    model = PingRecord
    collection_type = "gnms_ping"

    async def save_batch(
        self,
        switch_hostname: str,
        raw_data: str,
        parsed_items: list[BaseModel],
        maintenance_id: str,
    ) -> CollectionBatch | None:
        """
        差異寫入：比對 latest batch 中每筆 target 的 is_reachable，
        只寫入有變化的 record + 新增的 target。

        - 首次採集 → 建 batch + 全部 typed rows
        - hash 相同 → 只更新 last_checked_at
        - hash 不同 → 在同一個 batch 中 UPDATE 有變化的 record
        """
        from sqlalchemy import update

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
            # 完全沒變 → 只更新 last_checked_at
            latest.last_checked_at = now
            await self.session.flush()
            return None

        if not latest:
            # 首次採集 → 走原本的完整寫入
            return await super().save_batch(
                switch_hostname, raw_data, parsed_items, maintenance_id,
            )

        # ── 差異更新：讀取現有 batch 中的 record，比對變化 ──
        batch_id = latest.batch_id
        existing_stmt = select(PingRecord).where(
            PingRecord.batch_id == batch_id,
        )
        existing_result = await self.session.execute(existing_stmt)
        existing_records = {r.target: r for r in existing_result.scalars().all()}

        changed = 0
        for item in parsed_items:
            data = item.model_dump()
            target = data["target"]
            existing = existing_records.get(target)

            if existing is None:
                # 新 target → INSERT
                self.session.add(PingRecord(
                    batch_id=batch_id,
                    switch_hostname=switch_hostname,
                    maintenance_id=maintenance_id,
                    collected_at=now,
                    **data,
                ))
                changed += 1
            elif existing.is_reachable != data["is_reachable"]:
                # 狀態變化 → UPDATE
                existing.is_reachable = data["is_reachable"]
                existing.collected_at = now
                changed += 1

        # 更新 batch metadata
        batch_stmt = select(CollectionBatch).where(
            CollectionBatch.id == batch_id,
        )
        batch_result = await self.session.execute(batch_stmt)
        batch = batch_result.scalar_one_or_none()
        if batch:
            batch.collected_at = now
            batch.item_count = len(parsed_items)

        # 更新 latest 指標
        latest.data_hash = data_hash
        latest.collected_at = now
        latest.last_checked_at = now

        await self.session.flush()
        return batch if changed > 0 else None


# ── Factory ──────────────────────────────────────────────────────

TYPED_REPO_MAP: dict[str, type[TypedRecordRepository[Any]]] = {
    "get_gbic_details": TransceiverRecordRepo,
    "get_channel_group": PortChannelRecordRepo,
    "get_uplink": NeighborRecordRepo,
    "get_uplink_lldp": NeighborLldpRecordRepo,
    "get_uplink_cdp": NeighborCdpRecordRepo,
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
