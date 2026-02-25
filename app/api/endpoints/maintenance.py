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
from app.api.endpoints.auth import require_root, require_write, get_current_user, check_maintenance_access
from app.core.enums import UserRole
from app.services.system_log import write_log
from typing import Annotated
from sqlalchemy import text

from app.db.models import (
    # Config & Checkpoints
    Checkpoint,
    ReferenceClient,
    MaintenanceConfig,
    # Expectations
    UplinkExpectation,
    VersionExpectation,
    PortChannelExpectation,
    # Collection
    CollectionBatch,
    CollectionError,
    IndicatorResult,
    # Typed Records (named after production DB tables)
    TransceiverRecord,
    PortChannelRecord,
    NeighborRecord,
    InterfaceErrorRecord,
    InterfaceStatusRecord,
    StaticAclRecord,
    DynamicAclRecord,
    MacTableRecord,
    FanRecord,
    PowerRecord,
    VersionRecord,
    # Client
    ClientRecord,
    ClientComparison,
    ClientCategory,
    ClientCategoryMember,
    # Maintenance Lists
    MaintenanceMacList,
    MaintenanceDeviceList,
    # Contacts (通訊錄)
    Contact,
    ContactCategory,
    # Cases (案件)
    Case,
    CaseNote,
    # Meals (餐點)
    MealZone,
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
    active_seconds: float = 0.0
    max_seconds: float = 0.0
    remaining_seconds: float = 0.0


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
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """
    取得歲修 ID 列表。

    權限控制：
    - ROOT: 可看到所有歲修
    - PM/GUEST: 只能看到被指派的歲修
    """
    user_role = user.get("role")
    user_maintenance_id = user.get("maintenance_id")

    if user_role == UserRole.ROOT.value:
        # ROOT 可以看到所有歲修
        stmt = select(MaintenanceConfig).order_by(MaintenanceConfig.created_at.desc())
    else:
        # PM/GUEST 只能看到被指派的歲修
        if not user_maintenance_id:
            # 未被指派任何歲修，回傳空列表
            return []
        stmt = select(MaintenanceConfig).where(
            MaintenanceConfig.maintenance_id == user_maintenance_id
        )

    result = await session.execute(stmt)
    configs = result.scalars().all()

    from app.services.maintenance_time import _compute
    from app.core.config import settings

    max_seconds = settings.max_collection_days * 86400

    items = []
    for c in configs:
        active = _compute(
            is_active=c.is_active,
            accumulated=c.active_seconds_accumulated,
            last_activated_at=c.last_activated_at,
        )
        remaining = max(0.0, max_seconds - active)
        items.append({
            "id": c.maintenance_id,
            "name": c.name,
            "is_active": c.is_active,
            "created_at": c.created_at,
            "active_seconds": round(active, 1),
            "max_seconds": float(max_seconds),
            "remaining_seconds": round(remaining, 1),
        })

    return items


@router.post("", response_model=MaintenanceResponse)
async def create_maintenance(
    maintenance: MaintenanceCreate,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_root),
) -> dict:
    """建立新的歲修 ID。僅限 ROOT 使用者。"""
    
    # 檢查是否已存在
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance.id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="歲修 ID 已存在")
    
    from datetime import datetime, timezone

    config = MaintenanceConfig(
        maintenance_id=maintenance.id,
        name=maintenance.name,
        is_active=False,
        last_activated_at=None,
    )

    session.add(config)
    await session.commit()
    await session.refresh(config)

    await write_log(
        level="INFO",
        source="api",
        summary=f"建立歲修: {maintenance.id}",
        module="maintenance",
        maintenance_id=maintenance.id,
    )

    from app.core.config import settings as _settings
    _max = _settings.max_collection_days * 86400

    return {
        "id": config.maintenance_id,
        "name": config.name,
        "is_active": config.is_active,
        "created_at": config.created_at,
        "active_seconds": 0.0,
        "max_seconds": float(_max),
        "remaining_seconds": float(_max),
    }


@router.patch("/{maintenance_id}/toggle-active", response_model=MaintenanceResponse)
async def toggle_maintenance_active(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_root),
) -> dict:
    """切換歲修的採集狀態（暫停/恢復）。僅限 ROOT 使用者。"""
    from datetime import datetime, timezone

    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="歲修不存在")

    now = datetime.now(timezone.utc)

    if config.is_active:
        # 暫停：累加本段活躍時間，清除 last_activated_at
        if config.last_activated_at:
            # DB 可能回傳 naive datetime，統一轉為 aware
            last = config.last_activated_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (now - last).total_seconds()
            config.active_seconds_accumulated = (
                (config.active_seconds_accumulated or 0) + int(elapsed)
            )
        config.last_activated_at = None
        config.is_active = False

        # DB-based per-MAC hash 偵測，無需清除 in-memory cache
    else:
        # 恢復：記錄啟用時間
        config.last_activated_at = now
        config.is_active = True

    await session.commit()
    await session.refresh(config)

    # 寫入系統日誌
    action = "恢復採集" if config.is_active else "暫停採集"
    await write_log(
        level="info",
        source="maintenance",
        summary=f"歲修 {maintenance_id} {action}",
    )

    from app.services.maintenance_time import _compute
    from app.core.config import settings as _settings
    _max = _settings.max_collection_days * 86400
    active = _compute(
        is_active=config.is_active,
        accumulated=config.active_seconds_accumulated,
        last_activated_at=config.last_activated_at,
    )

    return {
        "id": config.maintenance_id,
        "name": config.name,
        "is_active": config.is_active,
        "created_at": config.created_at,
        "active_seconds": round(active, 1),
        "max_seconds": float(_max),
        "remaining_seconds": round(max(0.0, _max - active), 1),
    }


@router.delete("/{maintenance_id}")
async def delete_maintenance(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_root),
) -> dict:
    """刪除歲修 ID 及所有相關數據。僅限 ROOT 使用者。"""
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
        (PortChannelRecord, "port_channel_records"),
        (NeighborRecord, "neighbor_records"),
        (InterfaceErrorRecord, "interface_error_records"),
        (StaticAclRecord, "static_acl_records"),
        (DynamicAclRecord, "dynamic_acl_records"),
        (MacTableRecord, "mac_table_records"),
        (FanRecord, "fan_records"),
        (PowerRecord, "power_records"),
        (VersionRecord, "version_records"),
        (InterfaceStatusRecord, "interface_status_records"),
    ]
    for model, name in typed_records:
        result = await session.execute(
            delete(model).where(model.maintenance_id == maintenance_id)
        )
        deleted_counts[name] = result.rowcount

    # === 1.5 刪除可能存在的舊表（使用 raw SQL，忽略不存在的表）===
    # 嚴格允許清單 — 只有這些表名可以出現在 SQL 中
    _LEGACY_TABLE_ALLOWLIST = frozenset({
        "collection_records",
        "device_mappings",
        "interface_mappings",
        "uplink_records",
    })
    for table in _LEGACY_TABLE_ALLOWLIST:
        try:
            check_result = await session.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :tbl"),
                {"tbl": table}
            )
            if check_result.scalar() > 0:
                # table 來自上方 frozenset 常量，安全
                result = await session.execute(
                    text(f"DELETE FROM `{table}` WHERE maintenance_id = :mid"),
                    {"mid": maintenance_id}
                )
                deleted_counts[table] = result.rowcount
            else:
                deleted_counts[table] = 0
        except Exception:
            deleted_counts[table] = 0

    # === 1.7 刪除 LatestCollectionBatch ===
    from app.db.models import LatestCollectionBatch
    result = await session.execute(
        delete(LatestCollectionBatch).where(
            LatestCollectionBatch.maintenance_id == maintenance_id
        )
    )
    deleted_counts["latest_collection_batches"] = result.rowcount

    # === 1.8 刪除 CollectionError ===
    result = await session.execute(
        delete(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id
        )
    )
    deleted_counts["collection_errors"] = result.rowcount

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
        (PortChannelExpectation, "port_channel_expectations"),
    ]
    for model, name in expectations:
        result = await session.execute(
            delete(model).where(model.maintenance_id == maintenance_id)
        )
        deleted_counts[name] = result.rowcount

    # === 4. 刪除案件相關（先刪 case_notes，再刪 cases）===
    case_ids_stmt = select(Case.id).where(Case.maintenance_id == maintenance_id)
    case_ids_result = await session.execute(case_ids_stmt)
    case_ids = [row[0] for row in case_ids_result.fetchall()]

    if case_ids:
        result = await session.execute(
            delete(CaseNote).where(CaseNote.case_id.in_(case_ids))
        )
        deleted_counts["case_notes"] = result.rowcount
    else:
        deleted_counts["case_notes"] = 0

    result = await session.execute(
        delete(Case).where(Case.maintenance_id == maintenance_id)
    )
    deleted_counts["cases"] = result.rowcount

    # === 5. 刪除 Client 相關 ===
    from app.db.models import LatestClientRecord
    result = await session.execute(
        delete(LatestClientRecord).where(
            LatestClientRecord.maintenance_id == maintenance_id
        )
    )
    deleted_counts["latest_client_records"] = result.rowcount

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

    # === 7. 刪除通訊錄 (Contacts) ===
    # 先刪除聯絡人（FK 依賴 contact_categories）
    contact_cat_stmt = select(ContactCategory.id).where(
        ContactCategory.maintenance_id == maintenance_id
    )
    contact_cat_result = await session.execute(contact_cat_stmt)
    contact_category_ids = [row[0] for row in contact_cat_result.fetchall()]

    if contact_category_ids:
        result = await session.execute(
            delete(Contact).where(
                Contact.category_id.in_(contact_category_ids)
            )
        )
        deleted_counts["contacts"] = result.rowcount
    else:
        deleted_counts["contacts"] = 0

    result = await session.execute(
        delete(ContactCategory).where(
            ContactCategory.maintenance_id == maintenance_id
        )
    )
    deleted_counts["contact_categories"] = result.rowcount

    # === 8. 刪除餐點狀態 (Meals) ===
    result = await session.execute(
        delete(MealZone).where(
            MealZone.maintenance_id == maintenance_id
        )
    )
    deleted_counts["meal_zones"] = result.rowcount

    # === 9. 刪除該歲修的非 ROOT 使用者 ===
    # 每個歲修的使用者是一次性的，歲修結束後一併刪除
    from app.db.models import User
    result = await session.execute(
        delete(User).where(
            User.maintenance_id == maintenance_id,
            User.role != UserRole.ROOT,
        )
    )
    deleted_counts["users_deleted"] = result.rowcount

    # === 10. 最後刪除歲修配置本身 ===
    await session.delete(config)

    await session.commit()

    total_deleted = sum(deleted_counts.values())
    await write_log(
        level="WARNING",
        source="api",
        summary=f"刪除歲修: {maintenance_id} (共清除 {total_deleted} 筆資料)",
        module="maintenance",
        maintenance_id=maintenance_id,
    )

    return {
        "message": f"歲修 {maintenance_id} 及相關資料已刪除",
        "deleted_counts": deleted_counts,
    }


# ===== Checkpoint Endpoints =====

@router.post("/checkpoints", response_model=CheckpointResponse)
async def create_checkpoint(
    checkpoint: CheckpointCreate,
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

    await write_log(
        level="INFO",
        source=_user.get("username", "unknown"),
        summary=f"新增 Checkpoint「{checkpoint.name}」",
        module="maintenance",
        maintenance_id=checkpoint.maintenance_id,
    )

    return db_checkpoint.__dict__


@router.get("/checkpoints/{maintenance_id}", response_model=list[CheckpointResponse])
async def get_checkpoints(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """取得指定歲修的所有 checkpoints。"""
    check_maintenance_access(user, maintenance_id)

    stmt = select(Checkpoint).where(
        Checkpoint.maintenance_id == maintenance_id
    ).order_by(Checkpoint.checkpoint_time)

    result = await session.execute(stmt)
    checkpoints = result.scalars().all()

    return [cp.__dict__ for cp in checkpoints]


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(
    checkpoint_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """刪除 checkpoint。"""
    
    stmt = select(Checkpoint).where(Checkpoint.id == checkpoint_id)
    result = await session.execute(stmt)
    checkpoint = result.scalar_one_or_none()
    
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    cp_name = checkpoint.name
    cp_mid = checkpoint.maintenance_id

    await session.delete(checkpoint)
    await session.commit()

    await write_log(
        level="WARNING",
        source=_user.get("username", "unknown"),
        summary=f"刪除 Checkpoint「{cp_name}」",
        module="maintenance",
        maintenance_id=cp_mid,
    )

    return {"message": "Checkpoint deleted successfully"}


# ===== Reference Client Endpoints =====
# 不斷電機台現在以 maintenance_id 區分，每個歲修有獨立的清單

@router.get("/{maintenance_id}/reference-clients", response_model=list[ReferenceClientResponse])
async def get_reference_clients(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """取得指定歲修的所有不斷電機台。"""
    check_maintenance_access(user, maintenance_id)

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
    _user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """新增不斷電機台到指定歲修。"""
    check_maintenance_access(_user, maintenance_id)

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

    await write_log(
        level="INFO",
        source=_user.get("username", "unknown"),
        summary=f"新增不斷電機台: {db_client.mac_address}",
        module="maintenance",
        maintenance_id=maintenance_id,
    )

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
    _user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """刪除指定歲修的不斷電機台。"""
    check_maintenance_access(_user, maintenance_id)

    stmt = select(ReferenceClient).where(
        ReferenceClient.maintenance_id == maintenance_id,
        ReferenceClient.id == client_id,
    )
    result = await session.execute(stmt)
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Reference client not found")

    deleted_mac = client.mac_address

    client.is_active = False
    await session.commit()

    await write_log(
        level="WARNING",
        source=_user.get("username", "unknown"),
        summary=f"刪除不斷電機台: {deleted_mac}",
        module="maintenance",
        maintenance_id=maintenance_id,
    )

    return {"message": "Reference client deleted successfully"}


# ===== Maintenance Config Endpoints =====

@router.get("/config/{maintenance_id}")
async def get_maintenance_config(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """取得歲修配置（包含 anchor_time）。"""
    check_maintenance_access(user, maintenance_id)

    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        return {"maintenance_id": maintenance_id, "anchor_time": None}

    return {
        k: v for k, v in config.__dict__.items()
        if not k.startswith("_")
    }


@router.put("/config/{maintenance_id}")
async def update_maintenance_config(
    maintenance_id: str,
    config_update: MaintenanceConfigUpdate,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """更新歲修配置。"""
    check_maintenance_access(_user, maintenance_id)
    
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

    await write_log(
        level="INFO",
        source=_user.get("username", "unknown"),
        summary=f"更新歲修配置",
        module="maintenance",
        maintenance_id=maintenance_id,
    )

    return config.__dict__


@router.post("/{maintenance_id}/reset-timer")
async def reset_active_timer(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    重置歲修的活躍計時器。

    將 active_seconds_accumulated 歸零，並重設 last_activated_at。
    Mock API Server 會根據累計活躍時間決定故障出現時機。
    """
    from datetime import datetime, timezone

    check_maintenance_access(_user, maintenance_id)

    now_utc = datetime.now(timezone.utc)
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="找不到歲修配置")

    # 歸零累計活躍時間
    config.active_seconds_accumulated = 0
    if config.is_active:
        config.last_activated_at = now_utc
    await session.commit()

    await write_log(
        level="WARNING",
        source=_user.get("username", "unknown"),
        summary="重置活躍計時器",
        module="maintenance",
        maintenance_id=maintenance_id,
    )

    return {
        "success": True,
        "message": "活躍計時器已重置",
        "maintenance_id": maintenance_id,
        "active_seconds_accumulated": 0,
    }


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
    
    from datetime import datetime, timezone
    return {
        "total_switches": 0,
        "total_clients": 0,
        "indicators": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
