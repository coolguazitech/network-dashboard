"""
Client comparison endpoints.

客戶端新舊設備比較、時間點快照比較的 API 端點。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import settings
from app.db.base import get_async_session
from app.db.models import SeverityOverride
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


def _get_checkpoint_time_bucket(
    dt: datetime,
    interval_minutes: int,
) -> str:
    """
    根據 checkpoint 間隔計算時間桶的 key。

    Args:
        dt: 時間點
        interval_minutes: checkpoint 間隔（分鐘）

    Returns:
        時間桶的 key（用於分組）

    Examples:
        interval=60: 12:00, 12:30, 12:45 都會變成 "2024-01-01-12-00"
        interval=30: 12:00 -> "2024-01-01-12-00", 12:30 -> "2024-01-01-12-30"
        interval=15: 12:00 -> "2024-01-01-12-00", 12:15 -> "2024-01-01-12-15"
    """
    # 計算該時間點落在哪個時間桶
    bucket_minute = (dt.minute // interval_minutes) * interval_minutes
    return f"{dt.strftime('%Y-%m-%d-%H')}-{bucket_minute:02d}"


class SeverityOverrideCreate(BaseModel):
    """創建嚴重程度覆蓋的請求模型。"""
    mac_address: str
    override_severity: str  # 'critical', 'warning', 'info'
    original_severity: str | None = None
    note: str | None = None


router = APIRouter(
    prefix="/comparisons",
    tags=["comparisons"],
)

comparison_service = ClientComparisonService()


@router.get("/checkpoints/{maintenance_id}")
async def get_checkpoints(
    maintenance_id: str,
    max_days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="時間範圍（天），預設 7 天",
    ),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取 Checkpoint 列表（整點快照）。

    Checkpoint 是每小時的快照，用戶可選擇其中一個作為 Before 比較基準。
    預設使用第一個 Checkpoint 作為 Before。
    """
    from datetime import timedelta, timezone
    from sqlalchemy import func, distinct
    from app.db.models import ClientRecord, MaintenanceConfig
    from app.core.enums import MaintenancePhase

    # 獲取歲修配置
    config_stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    config_result = await session.execute(config_stmt)
    config = config_result.scalar_one_or_none()

    start_time = config.start_date if config else None

    # 計算截止時間（max_days 天前）
    from datetime import datetime
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

    # 獲取所有 NEW 階段的時間點
    stmt = (
        select(distinct(ClientRecord.collected_at))
        .where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
            ClientRecord.collected_at >= cutoff,
        )
        .order_by(ClientRecord.collected_at)
    )
    result = await session.execute(stmt)
    all_timepoints = result.scalars().all()

    # 根據設定的 checkpoint 間隔篩選時間桶（每個時間桶取最後一筆）
    interval_minutes = settings.checkpoint_interval_minutes
    time_bucket_checkpoints: dict[str, datetime] = {}
    for tp in all_timepoints:
        bucket_key = _get_checkpoint_time_bucket(tp, interval_minutes)
        time_bucket_checkpoints[bucket_key] = tp  # 該時間桶最後一筆

    checkpoints = sorted(time_bucket_checkpoints.values())

    # 台灣時區 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))

    return {
        "maintenance_id": maintenance_id,
        "start_time": start_time.isoformat() if start_time else None,
        "max_days": max_days,
        "checkpoint_count": len(checkpoints),
        "checkpoints": [
            {
                "timestamp": cp.isoformat(),
                # label 使用台灣時間顯示
                "label": cp.replace(tzinfo=timezone.utc).astimezone(tw_tz).strftime("%m/%d %H:00"),
                "is_default": i == 0,  # 第一個為預設
            }
            for i, cp in enumerate(checkpoints)
        ],
    }


@router.get("/checkpoints/{maintenance_id}/summaries")
async def get_checkpoint_summaries(
    maintenance_id: str,
    max_days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="時間範圍（天），預設 7 天",
    ),
    include_categories: bool = Query(
        default=False,
        description="是否包含按類別分組的統計（用於折線圖）",
    ),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    批量獲取每個 Checkpoint 的異常摘要。

    使用與 /diff 端點相同的比較邏輯，確保數字一致。
    當 include_categories=True 時，會額外回傳每個類別的異常數趨勢。
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, distinct
    from app.db.models import ClientRecord, MaintenanceMacList, ClientCategory, ClientCategoryMember

    # 計算截止時間
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

    # 獲取所有 checkpoint 時間點（整點）
    stmt = (
        select(distinct(ClientRecord.collected_at))
        .where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
            ClientRecord.collected_at >= cutoff,
        )
        .order_by(ClientRecord.collected_at)
    )
    result = await session.execute(stmt)
    all_timepoints = result.scalars().all()

    # 根據設定的 checkpoint 間隔篩選時間桶
    interval_minutes = settings.checkpoint_interval_minutes
    time_bucket_checkpoints: dict[str, datetime] = {}
    for tp in all_timepoints:
        bucket_key = _get_checkpoint_time_bucket(tp, interval_minutes)
        time_bucket_checkpoints[bucket_key] = tp

    checkpoints = sorted(time_bucket_checkpoints.values())

    if not checkpoints:
        return {
            "maintenance_id": maintenance_id,
            "summaries": {},
            "categories": [] if include_categories else None,
        }

    # 獲取最新快照時間
    latest_stmt = (
        select(func.max(ClientRecord.collected_at))
        .where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
        )
    )
    latest_result = await session.execute(latest_stmt)
    current_time = latest_result.scalar()

    if not current_time:
        return {
            "maintenance_id": maintenance_id,
            "summaries": {},
            "categories": [] if include_categories else None,
        }

    # 獲取 MAC 清單中註冊的總數
    mac_list_stmt = select(func.count()).select_from(MaintenanceMacList).where(
        MaintenanceMacList.maintenance_id == maintenance_id
    )
    mac_list_result = await session.execute(mac_list_stmt)
    registered_total = mac_list_result.scalar() or 0

    # 獲取覆蓋記錄
    override_stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id
    )
    override_result = await session.execute(override_stmt)
    overrides = override_result.scalars().all()
    override_map = {o.mac_address.upper(): o.override_severity for o in overrides}

    # 如果需要類別分組，獲取類別資訊
    categories_info = []
    mac_to_categories: dict[str, list[int]] = {}
    if include_categories:
        cat_stmt = select(ClientCategory).where(
            ClientCategory.is_active == True,
            ClientCategory.maintenance_id == maintenance_id,
        )
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()

        categories_info = [
            {"id": c.id, "name": c.name, "color": c.color}
            for c in categories
        ]

        # 獲取類別成員
        if categories:
            active_cat_ids = [c.id for c in categories]
            member_stmt = select(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(active_cat_ids)
            )
            member_result = await session.execute(member_stmt)
            members = member_result.scalars().all()
            for m in members:
                mac = m.mac_address.upper() if m.mac_address else ""
                if mac:
                    if mac not in mac_to_categories:
                        mac_to_categories[mac] = []
                    mac_to_categories[mac].append(m.category_id)

    # 計算每個 checkpoint 的摘要（使用與 /diff 相同的邏輯）
    summaries = {}

    # 排除等於 current_time 的 checkpoint（比較自己跟自己永遠是 0，沒有意義）
    # 允許 60 秒的容差，因為 checkpoint 時間可能與 current_time 相差幾秒
    valid_checkpoints = [
        cp for cp in checkpoints
        if abs((cp - current_time).total_seconds()) > 60
    ]

    for cp_time in valid_checkpoints:
        # 使用 comparison_service 生成比較結果
        comparisons = await comparison_service._generate_checkpoint_diff(
            maintenance_id=maintenance_id,
            checkpoint_time=cp_time,
            current_time=current_time,
            session=session,
        )

        # 計算異常數量（與 /diff 端點邏輯完全一致）
        issue_count = 0
        change_count = 0

        # 按類別統計
        category_issues: dict[int, int] = {}
        if include_categories:
            for cat in categories_info:
                category_issues[cat["id"]] = 0

        for comp in comparisons:
            mac = comp.mac_address.upper() if comp.mac_address else ""

            # 取得覆蓋後的 severity
            override_severity = override_map.get(mac)
            display_severity = override_severity if override_severity else comp.severity

            # 判斷是否為異常（與 /diff 邏輯一致）
            if display_severity == "info":
                is_issue = False
            elif display_severity == "undetected":
                is_issue = True
            else:
                is_issue = comp.is_changed or display_severity in ("critical", "warning")

            if comp.is_changed:
                change_count += 1

            if is_issue:
                issue_count += 1
                # 更新類別統計
                if include_categories:
                    cat_ids = mac_to_categories.get(mac, [])
                    for cat_id in cat_ids:
                        if cat_id in category_issues:
                            category_issues[cat_id] += 1

        summary_data = {
            "issue_count": issue_count,
            "change_count": change_count,
            "total": registered_total if registered_total > 0 else len(comparisons),
        }

        if include_categories:
            summary_data["by_category"] = category_issues

        summaries[cp_time.isoformat()] = summary_data

    response = {
        "maintenance_id": maintenance_id,
        "current_time": current_time.isoformat(),
        "summaries": summaries,
    }

    if include_categories:
        response["categories"] = categories_info

    return response


@router.get("/diff/{maintenance_id}")
async def get_diff(
    maintenance_id: str,
    checkpoint: str = Query(..., description="Checkpoint 時間（ISO 格式）作為 Before"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取 Checkpoint 與最新快照的差異比較。

    比較選定的 Checkpoint（Before）與最新 Snapshot（Current）之間的變化。
    兩者都來自 NEW 階段，用於追蹤歲修過程中設備狀態的變化。
    """
    from datetime import datetime
    from fastapi import HTTPException
    from app.db.models import ClientCategory, ClientCategoryMember

    try:
        checkpoint_time = datetime.fromisoformat(checkpoint)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"無效的時間格式: {checkpoint}，請使用 ISO 格式"
        )

    # 獲取最新快照時間
    from sqlalchemy import func
    from app.db.models import ClientRecord
    from app.core.enums import MaintenancePhase

    latest_stmt = (
        select(func.max(ClientRecord.collected_at))
        .where(
            ClientRecord.maintenance_id == maintenance_id,
            ClientRecord.phase == MaintenancePhase.NEW,
        )
    )
    latest_result = await session.execute(latest_stmt)
    current_time = latest_result.scalar()

    # 使用新的 Checkpoint vs Current 比較邏輯（都在 NEW 階段內）
    comparisons = await comparison_service._generate_checkpoint_diff(
        maintenance_id=maintenance_id,
        checkpoint_time=checkpoint_time,
        current_time=current_time,
        session=session,
    )

    # 獲取分類資訊
    cat_stmt = select(ClientCategory).where(
        ClientCategory.is_active == True,
        ClientCategory.maintenance_id == maintenance_id,
    )
    cat_result = await session.execute(cat_stmt)
    categories = cat_result.scalars().all()

    # 獲取分類成員
    active_cat_ids = [c.id for c in categories]
    mac_to_categories: dict[str, list[int]] = {}
    if active_cat_ids:
        member_stmt = select(ClientCategoryMember).where(
            ClientCategoryMember.category_id.in_(active_cat_ids)
        )
        member_result = await session.execute(member_stmt)
        members = member_result.scalars().all()
        for m in members:
            mac = m.mac_address.upper() if m.mac_address else ""
            if mac:
                if mac not in mac_to_categories:
                    mac_to_categories[mac] = []
                mac_to_categories[mac].append(m.category_id)

    # 獲取覆蓋記錄（完整物件，用於判斷 is_overridden）
    override_stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id
    )
    override_result = await session.execute(override_stmt)
    overrides = override_result.scalars().all()
    override_map = {o.mac_address.upper(): o for o in overrides}

    # 獲取 MAC 清單中註冊的總數
    from app.db.models import MaintenanceMacList
    mac_list_stmt = select(func.count()).select_from(MaintenanceMacList).where(
        MaintenanceMacList.maintenance_id == maintenance_id
    )
    mac_list_result = await session.execute(mac_list_stmt)
    registered_total = mac_list_result.scalar() or 0

    # 計算統計（優先使用 MAC 清單總數）
    total = registered_total if registered_total > 0 else len(comparisons)
    has_issues = 0
    by_category: dict[int | None, dict] = {}

    # 初始化分類統計
    by_category[-1] = {"id": -1, "name": "全部", "color": "#1F2937", "total": 0, "issues": 0}
    for cat in categories:
        by_category[cat.id] = {"id": cat.id, "name": cat.name, "color": cat.color, "total": 0, "issues": 0}
    by_category[None] = {"id": None, "name": "未分類", "color": "#6B7280", "total": 0, "issues": 0}

    results = []
    for comp in comparisons:
        mac = comp.mac_address.upper() if comp.mac_address else ""
        cat_ids = mac_to_categories.get(mac, [None])
        if not cat_ids:
            cat_ids = [None]

        # 取得覆蓋資訊
        override = override_map.get(mac)
        is_overridden = override is not None
        auto_severity = comp.severity  # 自動判斷的嚴重程度
        display_severity = override.override_severity if override else comp.severity
        original_severity = override.original_severity if override else None

        # 判斷是否為異常：使用覆蓋後的 severity
        # 如果被覆蓋為 info（正常），則不算異常
        if display_severity == "info":
            is_issue = False
        elif display_severity == "undetected":
            is_issue = True
        else:
            # critical/warning 或有變化都算異常
            is_issue = comp.is_changed or display_severity in ("critical", "warning")

        if is_issue:
            has_issues += 1

        # 更新分類統計
        by_category[-1]["total"] += 1
        if is_issue:
            by_category[-1]["issues"] += 1

        for cat_id in cat_ids:
            if cat_id in by_category:
                by_category[cat_id]["total"] += 1
                if is_issue:
                    by_category[cat_id]["issues"] += 1

        # 構建結果
        results.append({
            "mac_address": comp.mac_address,
            "category_ids": cat_ids,
            "is_changed": comp.is_changed,
            "is_issue": is_issue,
            "severity": display_severity,
            "auto_severity": auto_severity,
            "is_overridden": is_overridden,
            "original_severity": original_severity,
            "differences": comp.differences,
            "before": {
                "ip_address": comp.old_ip_address,
                "switch_hostname": comp.old_switch_hostname,
                "interface_name": comp.old_interface_name,
                "speed": comp.old_speed,
                "duplex": comp.old_duplex,
                "link_status": comp.old_link_status,
                "ping_reachable": comp.old_ping_reachable,
                "acl_passes": comp.old_acl_passes,
            },
            "current": {
                "ip_address": comp.new_ip_address,
                "switch_hostname": comp.new_switch_hostname,
                "interface_name": comp.new_interface_name,
                "speed": comp.new_speed,
                "duplex": comp.new_duplex,
                "link_status": comp.new_link_status,
                "ping_reachable": comp.new_ping_reachable,
                "acl_passes": comp.new_acl_passes,
            },
        })

    return {
        "maintenance_id": maintenance_id,
        "checkpoint_time": checkpoint_time.isoformat(),
        "current_time": current_time.isoformat() if current_time else None,
        "summary": {
            "total": total,
            "has_issues": has_issues,
            "normal": total - has_issues,
        },
        "by_category": list(by_category.values()),
        "results": results,
    }


@router.get("/summary/{maintenance_id}")
async def get_comparison_summary(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取客戶端比較結果的摘要。
    
    返回統計信息：總數、未變化數、變化數、嚴重程度分布等。
    """
    try:
        summary = await comparison_service.get_comparison_summary(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"獲取摘要失敗: {str(e)}",
        )


@router.get("/list/{maintenance_id}")
async def list_comparisons(
    maintenance_id: str,
    before_time: str | None = Query(None, description="BEFORE 時間點（ISO 格式）"),
    mac_address: str | None = Query(None, description="按 MAC 地址篩選（已廢棄，請使用 search_text）"),
    search_text: str | None = Query(None, description="搜尋 MAC 地址或 IP 地址"),
    severity: str | None = Query(None, description="按嚴重程度篩選 (critical/warning/info/undetected)"),
    changed_only: bool = Query(False, description="只返回有變化的結果"),
    include_undetected: bool = Query(True, description="是否包含分類成員中未偵測的 MAC"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出客戶端比較結果。
    
    支持按 MAC 地址、IP 地址、嚴重程度和是否變化進行篩選。
    包含分類成員中未偵測到的 MAC（severity='undetected'）。
    """
    from sqlalchemy import select
    from app.db.models import ClientCategoryMember
    
    try:
        # 向後兼容：如果提供 mac_address 但沒有 search_text，使用 mac_address
        search = search_text or mac_address
        
        comparisons = await comparison_service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            search_text=search,
            severity=severity if severity != 'undetected' else None,
            changed_only=changed_only,
            before_time=before_time,
        )
        
        # 建立已偵測到的 MAC 集合
        detected_macs = {
            comp.mac_address.upper() for comp in comparisons 
            if comp.mac_address
        }
        
        # 獲取所有覆蓋記錄
        override_stmt = select(SeverityOverride).where(
            SeverityOverride.maintenance_id == maintenance_id
        )
        override_result = await session.execute(override_stmt)
        overrides = override_result.scalars().all()
        
        # 建立 MAC -> 覆蓋記錄 對照
        override_map = {
            o.mac_address.upper(): o for o in overrides
        }
        
        # 轉換為字典格式
        results = []
        
        def has_any_data(comp, prefix: str) -> bool:
            """檢查指定前綴（old/new）是否有任何有效數據。"""
            fields = [
                f"{prefix}_switch_hostname",
                f"{prefix}_interface_name",
                f"{prefix}_ip_address",
                f"{prefix}_vlan_id",
                f"{prefix}_speed",
                f"{prefix}_duplex",
                f"{prefix}_link_status",
            ]
            for field in fields:
                value = getattr(comp, field, None)
                if value is not None and value != "":
                    return True
            return False
        
        for comp in comparisons:
            # 判斷偵測狀態（使用更全面的檢查）
            old_detected = has_any_data(comp, 'old')
            new_detected = has_any_data(comp, 'new')
            
            # 檢查是否有手動覆蓋
            normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
            override = override_map.get(normalized_mac)
            
            # 決定最終顯示的 severity
            display_severity = comp.severity
            is_overridden = False
            original_severity = None
            override_note = None
            
            if override:
                is_overridden = True
                original_severity = override.original_severity or comp.severity
                display_severity = override.override_severity
                override_note = override.note
            
            results.append({
                "id": comp.id,
                "mac_address": comp.mac_address,
                "is_changed": comp.is_changed,
                "severity": display_severity,
                "auto_severity": comp.severity,  # 保留原始自動判斷值
                "is_overridden": is_overridden,
                "original_severity": original_severity,
                "override_note": override_note,
                "differences": comp.differences,
                "notes": comp.notes,
                "old_detected": old_detected,
                "new_detected": new_detected,
                "old": {
                    "ip_address": comp.old_ip_address,
                    "switch_hostname": comp.old_switch_hostname,
                    "interface_name": comp.old_interface_name,
                    "vlan_id": comp.old_vlan_id,
                    "speed": comp.old_speed,
                    "duplex": comp.old_duplex,
                    "link_status": comp.old_link_status,
                    "ping_reachable": comp.old_ping_reachable,
                    "acl_passes": comp.old_acl_passes,
                },
                "new": {
                    "ip_address": comp.new_ip_address,
                    "switch_hostname": comp.new_switch_hostname,
                    "interface_name": comp.new_interface_name,
                    "vlan_id": comp.new_vlan_id,
                    "speed": comp.new_speed,
                    "duplex": comp.new_duplex,
                    "link_status": comp.new_link_status,
                    "ping_reachable": comp.new_ping_reachable,
                    "acl_passes": comp.new_acl_passes,
                },
                "collected_at": comp.collected_at.isoformat() if comp.collected_at else None,
            })
        
        # 如果需要包含未偵測的 MAC
        if include_undetected:
            from app.db.models import ClientCategory
            
            # 只獲取該歲修下活躍分類的成員（必須過濾 maintenance_id）
            active_cat_stmt = select(ClientCategory.id).where(
                ClientCategory.is_active == True,
                ClientCategory.maintenance_id == maintenance_id,
            )
            active_cat_result = await session.execute(active_cat_stmt)
            active_cat_ids = [row[0] for row in active_cat_result.fetchall()]
            
            member_stmt = (
                select(ClientCategoryMember)
                .where(ClientCategoryMember.category_id.in_(active_cat_ids))
            )
            member_result = await session.execute(member_stmt)
            members = member_result.scalars().all()
            
            # 使用 set 避免重複添加（一個 MAC 可能在多個分類中）
            added_undetected_macs = set()
            
            # 添加未偵測的 MAC
            for member in members:
                normalized_mac = member.mac_address.upper() if member.mac_address else ""
                # 跳過已偵測或已添加的 MAC
                if not normalized_mac:
                    continue
                if normalized_mac in detected_macs:
                    continue
                if normalized_mac in added_undetected_macs:
                    continue
                added_undetected_macs.add(normalized_mac)
                
                # 檢查搜尋條件
                if search:
                    search_lower = search.lower()
                    if search_lower not in normalized_mac.lower():
                        continue
                
                # 檢查是否有覆蓋
                override = override_map.get(normalized_mac)
                display_severity = "undetected"
                is_overridden = False
                original_severity = None
                override_note = None
                
                if override:
                    is_overridden = True
                    original_severity = "undetected"  # 原始一定是 undetected
                    display_severity = override.override_severity
                    override_note = override.note
                
                # 如果篩選 severity，需要匹配覆蓋後的 severity
                if severity:
                    if severity == 'undetected':
                        # 只顯示沒有覆蓋或覆蓋值仍為 undetected 的
                        if is_overridden and display_severity != 'undetected':
                            continue
                    else:
                        # 篩選其他 severity
                        if display_severity != severity:
                            continue
                
                results.append({
                        "id": None,
                        "mac_address": normalized_mac,
                        "is_changed": False,
                        "severity": display_severity,
                        "auto_severity": "undetected",
                        "is_overridden": is_overridden,
                        "original_severity": original_severity,
                        "override_note": override_note,
                        "differences": {},
                        "notes": "此 MAC 在 OLD 和 NEW 階段均未偵測到",
                        "old_detected": False,
                        "new_detected": False,
                        "old": {
                            "ip_address": None,
                            "switch_hostname": None,
                            "interface_name": None,
                            "vlan_id": None,
                            "speed": None,
                            "duplex": None,
                            "link_status": None,
                            "ping_reachable": None,
                            "acl_passes": None,
                        },
                        "new": {
                            "ip_address": None,
                            "switch_hostname": None,
                            "interface_name": None,
                            "vlan_id": None,
                            "speed": None,
                            "duplex": None,
                            "link_status": None,
                            "ping_reachable": None,
                            "acl_passes": None,
                        },
                        "collected_at": None,
                        "description": member.description,
                    })
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"列出比較結果失敗: {str(e)}",
        )


@router.get("/detail/{maintenance_id}/{mac_address}")
async def get_comparison_detail(
    maintenance_id: str,
    mac_address: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取單個客戶端的詳細比較結果。
    """
    try:
        comparisons = await comparison_service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            search_text=mac_address,
        )
        
        if not comparisons:
            raise HTTPException(
                status_code=404,
                detail=f"未找到 MAC 地址為 {mac_address} 的比較記錄",
            )
        
        comp = comparisons[0]
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "mac_address": mac_address,
            "is_changed": comp.is_changed,
            "severity": comp.severity,
            "differences": comp.differences,
            "notes": comp.notes,
            "old": {
                "ip_address": comp.old_ip_address,
                "switch_hostname": comp.old_switch_hostname,
                "interface_name": comp.old_interface_name,
                "vlan_id": comp.old_vlan_id,
                "speed": comp.old_speed,
                "duplex": comp.old_duplex,
                "link_status": comp.old_link_status,
                "ping_reachable": comp.old_ping_reachable,
                "acl_passes": comp.old_acl_passes,
            },
            "new": {
                "ip_address": comp.new_ip_address,
                "switch_hostname": comp.new_switch_hostname,
                "interface_name": comp.new_interface_name,
                "vlan_id": comp.new_vlan_id,
                "speed": comp.new_speed,
                "duplex": comp.new_duplex,
                "link_status": comp.new_link_status,
                "ping_reachable": comp.new_ping_reachable,
                "acl_passes": comp.new_acl_passes,
            },
            "collected_at": comp.collected_at.isoformat() if comp.collected_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"獲取詳細比較結果失敗: {str(e)}",
        )


# ========== 嚴重程度覆蓋 API ==========

@router.get("/overrides/{maintenance_id}")
async def list_severity_overrides(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """列出所有嚴重程度覆蓋記錄。"""
    stmt = (
        select(SeverityOverride)
        .where(SeverityOverride.maintenance_id == maintenance_id)
        .order_by(SeverityOverride.updated_at.desc())
    )
    result = await session.execute(stmt)
    overrides = result.scalars().all()
    
    return {
        "success": True,
        "maintenance_id": maintenance_id,
        "count": len(overrides),
        "overrides": [
            {
                "id": o.id,
                "mac_address": o.mac_address,
                "override_severity": o.override_severity,
                "original_severity": o.original_severity,
                "note": o.note,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in overrides
        ],
    }


@router.post("/overrides/{maintenance_id}")
async def create_or_update_severity_override(
    maintenance_id: str,
    data: SeverityOverrideCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    創建或更新嚴重程度覆蓋。
    
    如果該 MAC 已有覆蓋記錄則更新，否則創建新記錄。
    """
    # 標準化 MAC 地址
    normalized_mac = data.mac_address.upper()
    
    # 驗證 severity 值
    valid_severities = ['critical', 'warning', 'info']
    if data.override_severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"無效的嚴重程度，必須是: {', '.join(valid_severities)}",
        )
    
    # 查詢是否已存在
    stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id,
        SeverityOverride.mac_address == normalized_mac,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        # 更新現有記錄
        existing.override_severity = data.override_severity
        if data.note is not None:
            existing.note = data.note
        # 保留 original_severity 不變
        await session.commit()
        await session.refresh(existing)
        override = existing
        message = "覆蓋記錄已更新"
    else:
        # 創建新記錄
        override = SeverityOverride(
            maintenance_id=maintenance_id,
            mac_address=normalized_mac,
            override_severity=data.override_severity,
            original_severity=data.original_severity,
            note=data.note,
        )
        session.add(override)
        await session.commit()
        await session.refresh(override)
        message = "覆蓋記錄已創建"
    
    return {
        "success": True,
        "message": message,
        "override": {
            "id": override.id,
            "mac_address": override.mac_address,
            "override_severity": override.override_severity,
            "original_severity": override.original_severity,
            "note": override.note,
        },
    }


@router.delete("/overrides/{maintenance_id}/{mac_address}")
async def delete_severity_override(
    maintenance_id: str,
    mac_address: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """刪除嚴重程度覆蓋（恢復自動判斷）。"""
    normalized_mac = mac_address.upper()
    
    stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id,
        SeverityOverride.mac_address == normalized_mac,
    )
    result = await session.execute(stmt)
    override = result.scalar_one_or_none()
    
    if not override:
        raise HTTPException(
            status_code=404,
            detail=f"找不到 MAC {mac_address} 的覆蓋記錄",
        )
    
    original = override.original_severity
    await session.delete(override)
    await session.commit()
    
    return {
        "success": True,
        "message": "已恢復自動判斷",
        "mac_address": normalized_mac,
        "original_severity": original,
    }


@router.delete("/overrides/{maintenance_id}")
async def clear_all_severity_overrides(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """清除所有嚴重程度覆蓋（恢復全部自動判斷）。"""
    stmt = delete(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    await session.commit()
    
    return {
        "success": True,
        "message": f"已清除 {result.rowcount} 筆覆蓋記錄",
        "deleted_count": result.rowcount,
    }
