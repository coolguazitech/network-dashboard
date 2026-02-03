"""
Checkpoint and Reference Client API endpoints.

提供 checkpoint 管理和不斷電機台配置的 API。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from sqlalchemy import text

from app.db.models import (
    # Config & Checkpoints
    Checkpoint,
    ReferenceClient,
    MaintenanceConfig,
    # Expectations
    UplinkExpectation,
    VersionExpectation,
    ArpSource,
    PortChannelExpectation,
    # Collection
    CollectionBatch,
    IndicatorResult,
    # Typed Records
    TransceiverRecord,
    VersionRecord,
    FanRecord,
    PowerRecord,
    PortChannelRecord,
    PingRecord,
    NeighborRecord,
    InterfaceErrorRecord,
    # Client
    ClientRecord,
    ClientComparison,
    SeverityOverride,
    ClientCategory,
    ClientCategoryMember,
    # Maintenance Lists
    MaintenanceMacList,
    MaintenanceDeviceList,
)


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


# ===== Pydantic Models =====

class MaintenanceCreate(BaseModel):
    id: str
    name: str | None = None


class MaintenanceResponse(BaseModel):
    id: str
    name: str | None
    is_active: bool
    created_at: datetime


class CheckpointCreate(BaseModel):
    maintenance_id: str
    name: str
    checkpoint_time: datetime
    description: str | None = None
    created_by: str | None = None


class CheckpointResponse(BaseModel):
    id: int
    maintenance_id: str
    name: str
    checkpoint_time: datetime
    description: str | None
    summary_data: dict[str, Any] | None
    created_by: str | None
    created_at: datetime


class ReferenceClientCreate(BaseModel):
    mac_address: str
    description: str | None = None
    location: str | None = None
    reason: str | None = None


class ReferenceClientResponse(BaseModel):
    id: int
    maintenance_id: str
    mac_address: str
    description: str | None
    location: str | None
    reason: str | None
    is_active: bool


class MaintenanceConfigUpdate(BaseModel):
    anchor_time: datetime | None = None
    config_data: dict[str, Any] | None = None


# ===== Maintenance ID Endpoints =====

@router.get("", response_model=list[MaintenanceResponse])
async def list_maintenances(
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """取得所有歲修 ID 列表。"""
    
    stmt = select(MaintenanceConfig).order_by(MaintenanceConfig.created_at.desc())
    result = await session.execute(stmt)
    configs = result.scalars().all()
    
    return [
        {
            "id": c.maintenance_id,
            "name": c.config_data.get("name") if c.config_data else None,
            "is_active": c.config_data.get("is_active", True) if c.config_data else True,
            "created_at": c.created_at,
        }
        for c in configs
    ]


@router.post("", response_model=MaintenanceResponse)
async def create_maintenance(
    maintenance: MaintenanceCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """建立新的歲修 ID。"""
    
    # 檢查是否已存在
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance.id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="歲修 ID 已存在")
    
    config = MaintenanceConfig(
        maintenance_id=maintenance.id,
        config_data={
            "name": maintenance.name,
            "is_active": True,
        },
    )
    
    session.add(config)
    await session.commit()
    await session.refresh(config)
    
    return {
        "id": config.maintenance_id,
        "name": maintenance.name,
        "is_active": True,
        "created_at": config.created_at,
    }


@router.delete("/{maintenance_id}")
async def delete_maintenance(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """刪除歲修 ID 及所有相關數據。"""
    # 查找歲修配置
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="歲修 ID 不存在")
    
    deleted_counts = {}

    # === 1. 刪除 Typed Records（採集記錄，先刪子表）===
    typed_records = [
        (TransceiverRecord, "transceiver_records"),
        (VersionRecord, "version_records"),
        (FanRecord, "fan_records"),
        (PowerRecord, "power_records"),
        (PortChannelRecord, "port_channel_records"),
        (PingRecord, "ping_records"),
        (NeighborRecord, "neighbor_records"),
        (InterfaceErrorRecord, "interface_error_records"),
    ]
    for model, name in typed_records:
        result = await session.execute(
            delete(model).where(model.maintenance_id == maintenance_id)
        )
        deleted_counts[name] = result.rowcount

    # === 1.5 刪除可能存在的舊表（使用 raw SQL，忽略不存在的表）===
    raw_sql_tables = [
        "collection_records",
        "device_mappings",
        "interface_mappings",
        "uplink_records",
    ]
    for table in raw_sql_tables:
        try:
            # 先檢查表是否存在
            check_result = await session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :tbl"),
                {"tbl": table}
            )
            if check_result.scalar() > 0:
                result = await session.execute(
                    text(f"DELETE FROM {table} WHERE maintenance_id = :mid"),
                    {"mid": maintenance_id}
                )
                deleted_counts[table] = result.rowcount
            else:
                deleted_counts[table] = 0
        except Exception:
            # 忽略任何錯誤
            deleted_counts[table] = 0

    # === 2. 刪除 CollectionBatch ===
    result = await session.execute(
        delete(CollectionBatch).where(
            CollectionBatch.maintenance_id == maintenance_id
        )
    )
    deleted_counts["collection_batches"] = result.rowcount

    # === 3. 刪除期望值 ===
    expectations = [
        (UplinkExpectation, "uplink_expectations"),
        (VersionExpectation, "version_expectations"),
        (ArpSource, "arp_sources"),
        (PortChannelExpectation, "port_channel_expectations"),
    ]
    for model, name in expectations:
        result = await session.execute(
            delete(model).where(model.maintenance_id == maintenance_id)
        )
        deleted_counts[name] = result.rowcount

    # === 4. 刪除 Client 相關 ===
    result = await session.execute(
        delete(ClientRecord).where(
            ClientRecord.maintenance_id == maintenance_id
        )
    )
    deleted_counts["client_records"] = result.rowcount

    result = await session.execute(
        delete(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
    )
    deleted_counts["client_comparisons"] = result.rowcount

    result = await session.execute(
        delete(SeverityOverride).where(
            SeverityOverride.maintenance_id == maintenance_id
        )
    )
    deleted_counts["severity_overrides"] = result.rowcount

    # 先刪除分類成員（FK 依賴 client_categories）
    # 取得該歲修的所有分類 ID
    cat_stmt = select(ClientCategory.id).where(
        ClientCategory.maintenance_id == maintenance_id
    )
    cat_result = await session.execute(cat_stmt)
    category_ids = [row[0] for row in cat_result.fetchall()]

    if category_ids:
        result = await session.execute(
            delete(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(category_ids)
            )
        )
        deleted_counts["client_category_members"] = result.rowcount
    else:
        deleted_counts["client_category_members"] = 0

    result = await session.execute(
        delete(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id
        )
    )
    deleted_counts["client_categories"] = result.rowcount

    # === 5. 刪除 Maintenance 資料清單 ===
    result = await session.execute(
        delete(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
    )
    deleted_counts["mac_list"] = result.rowcount

    result = await session.execute(
        delete(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
    )
    deleted_counts["device_list"] = result.rowcount

    # === 6. 刪除 Checkpoint、ReferenceClient 和 IndicatorResult ===
    result = await session.execute(
        delete(Checkpoint).where(
            Checkpoint.maintenance_id == maintenance_id
        )
    )
    deleted_counts["checkpoints"] = result.rowcount

    result = await session.execute(
        delete(ReferenceClient).where(
            ReferenceClient.maintenance_id == maintenance_id
        )
    )
    deleted_counts["reference_clients"] = result.rowcount

    result = await session.execute(
        delete(IndicatorResult).where(
            IndicatorResult.maintenance_id == maintenance_id
        )
    )
    deleted_counts["indicator_results"] = result.rowcount

    # === 7. 最後刪除歲修配置本身 ===
    await session.delete(config)
    
    await session.commit()
    
    return {
        "message": f"歲修 {maintenance_id} 及相關資料已刪除",
        "deleted_counts": deleted_counts,
    }


# ===== Checkpoint Endpoints =====

@router.post("/checkpoints", response_model=CheckpointResponse)
async def create_checkpoint(
    checkpoint: CheckpointCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """創建新的 checkpoint。"""
    
    # TODO: 生成摘要數據
    summary_data = await _generate_checkpoint_summary(
        checkpoint.maintenance_id,
        checkpoint.checkpoint_time,
        session,
    )
    
    db_checkpoint = Checkpoint(
        maintenance_id=checkpoint.maintenance_id,
        name=checkpoint.name,
        checkpoint_time=checkpoint.checkpoint_time,
        description=checkpoint.description,
        summary_data=summary_data,
        created_by=checkpoint.created_by,
    )
    
    session.add(db_checkpoint)
    await session.commit()
    await session.refresh(db_checkpoint)
    
    return db_checkpoint.__dict__


@router.get("/checkpoints/{maintenance_id}", response_model=list[CheckpointResponse])
async def get_checkpoints(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """取得指定歲修的所有 checkpoints。"""
    
    stmt = select(Checkpoint).where(
        Checkpoint.maintenance_id == maintenance_id
    ).order_by(Checkpoint.checkpoint_time)
    
    result = await session.execute(stmt)
    checkpoints = result.scalars().all()
    
    return [cp.__dict__ for cp in checkpoints]


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(
    checkpoint_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """刪除 checkpoint。"""
    
    stmt = select(Checkpoint).where(Checkpoint.id == checkpoint_id)
    result = await session.execute(stmt)
    checkpoint = result.scalar_one_or_none()
    
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    
    await session.delete(checkpoint)
    await session.commit()
    
    return {"message": "Checkpoint deleted successfully"}


# ===== Reference Client Endpoints =====
# 不斷電機台現在以 maintenance_id 區分，每個歲修有獨立的清單

@router.get("/{maintenance_id}/reference-clients", response_model=list[ReferenceClientResponse])
async def get_reference_clients(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """取得指定歲修的所有不斷電機台。"""

    stmt = select(ReferenceClient).where(
        ReferenceClient.maintenance_id == maintenance_id,
        ReferenceClient.is_active == True,  # noqa: E712
    )
    result = await session.execute(stmt)
    clients = result.scalars().all()

    return [
        {
            "id": c.id,
            "maintenance_id": c.maintenance_id,
            "mac_address": c.mac_address,
            "description": c.description,
            "location": c.location,
            "reason": c.reason,
            "is_active": c.is_active,
        }
        for c in clients
    ]


@router.post("/{maintenance_id}/reference-clients", response_model=ReferenceClientResponse)
async def create_reference_client(
    maintenance_id: str,
    client: ReferenceClientCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """新增不斷電機台到指定歲修。"""

    # 檢查是否已存在相同 MAC
    existing_stmt = select(ReferenceClient).where(
        ReferenceClient.maintenance_id == maintenance_id,
        ReferenceClient.mac_address == client.mac_address.upper(),
    )
    existing_result = await session.execute(existing_stmt)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"MAC {client.mac_address} 已存在於此歲修的不斷電機台清單中"
        )

    db_client = ReferenceClient(
        maintenance_id=maintenance_id,
        mac_address=client.mac_address.upper(),
        description=client.description,
        location=client.location,
        reason=client.reason,
    )

    session.add(db_client)
    await session.commit()
    await session.refresh(db_client)

    return {
        "id": db_client.id,
        "maintenance_id": db_client.maintenance_id,
        "mac_address": db_client.mac_address,
        "description": db_client.description,
        "location": db_client.location,
        "reason": db_client.reason,
        "is_active": db_client.is_active,
    }


@router.delete("/{maintenance_id}/reference-clients/{client_id}")
async def delete_reference_client(
    maintenance_id: str,
    client_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """刪除指定歲修的不斷電機台。"""

    stmt = select(ReferenceClient).where(
        ReferenceClient.maintenance_id == maintenance_id,
        ReferenceClient.id == client_id,
    )
    result = await session.execute(stmt)
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Reference client not found")

    client.is_active = False
    await session.commit()

    return {"message": "Reference client deleted successfully"}


# ===== Maintenance Config Endpoints =====

@router.get("/config/{maintenance_id}")
async def get_maintenance_config(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """取得歲修配置（包含 anchor_time）。"""
    
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        return {"maintenance_id": maintenance_id, "anchor_time": None}
    
    return config.__dict__


@router.put("/config/{maintenance_id}")
async def update_maintenance_config(
    maintenance_id: str,
    config_update: MaintenanceConfigUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """更新歲修配置。"""
    
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        config = MaintenanceConfig(maintenance_id=maintenance_id)
        session.add(config)
    
    if config_update.anchor_time is not None:
        config.anchor_time = config_update.anchor_time
    
    if config_update.config_data is not None:
        config.config_data = config_update.config_data
    
    await session.commit()
    await session.refresh(config)
    
    return config.__dict__


# ===== Helper Functions =====

async def _generate_checkpoint_summary(
    maintenance_id: str,
    checkpoint_time: datetime,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    生成 checkpoint 的摘要數據。
    
    TODO: 實現詳細的統計邏輯
    """
    # 這裡應該查詢該時間點附近的各項指標數據
    # 並生成統計摘要
    
    return {
        "total_switches": 0,
        "total_clients": 0,
        "indicators": {},
        "generated_at": datetime.utcnow().isoformat(),
    }
