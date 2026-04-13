"""
Cases API endpoints.

案件管理 API 端點：查詢、更新、筆記、變化時間線、匯出 CSV。
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case as sql_case, select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.db.models import (
    Case, ClientRecord, LatestClientRecord, MaintenanceMacList,
)
from app.api.endpoints.auth import get_current_user, require_write
from app.services.case_service import (
    ATTRIBUTE_LABELS, CaseService, TRACKED_ATTRIBUTES,
)
from app.core.config import settings
from app.services.system_log import write_log


router = APIRouter(prefix="/cases", tags=["Cases"])

_svc = CaseService()


# ── Request / Response Models ──────────────────────────────────


class CaseUpdateRequest(BaseModel):
    summary: str | None = None
    status: str | None = None
    assignee: str | None = None


class CaseNoteCreateRequest(BaseModel):
    content: str


class CaseNoteUpdateRequest(BaseModel):
    content: str


# ── Endpoints ──────────────────────────────────────────────────


@router.get("/{maintenance_id}")
async def list_cases(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    assignee: str | None = Query(None, description="篩選負責人"),
    status: str | None = Query(None, description="篩選狀態"),
    ping_reachable: bool | None = Query(None, description="篩選 Ping 狀態"),
    search: str | None = Query(None, description="搜尋 MAC、IP 或備註"),
    include_resolved: bool = Query(False, description="是否包含已解決案件"),
    page: int = Query(1, ge=1, description="頁碼"),
    page_size: int = Query(50, ge=1, le=200, description="每頁筆數"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """列出指定歲修的所有案件（預設排除已解決，含分頁）。"""
    result = await _svc.get_cases(
        maintenance_id=maintenance_id,
        session=session,
        assignee=assignee,
        status=status,
        ping_reachable=ping_reachable,
        search=search,
        include_resolved=include_resolved,
        page=page,
        page_size=page_size,
    )
    return {"success": True, **result}


@router.get("/{maintenance_id}/stats")
async def get_case_stats(
    maintenance_id: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """取得案件統計。"""
    stats = await _svc.get_case_stats(maintenance_id, session)
    return {"success": True, **stats}


@router.post("/{maintenance_id}/sync")
async def sync_cases(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """同步案件與 MAC 清單（僅 ROOT/PM 可執行）。"""
    result = await _svc.sync_cases(maintenance_id, session)

    if result["created"] > 0:
        await write_log(
            level="INFO",
            source="api",
            summary=f"同步案件: 新增 {result['created']} 筆",
            module="cases",
            maintenance_id=maintenance_id,
        )

    return {"success": True, **result}


@router.get("/{maintenance_id}/export-csv")
async def export_cases_csv(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    status: str | None = Query(None, description="篩選狀態"),
    assignee: str | None = Query(None, description="篩選負責人"),
    search: str | None = Query(None, description="搜尋 MAC、IP 或備註"),
    ping_reachable: bool | None = Query(None, description="篩選 Ping 狀態"),
    include_resolved: bool = Query(False, description="是否包含已解決案件"),
    session: AsyncSession = Depends(get_async_session),
):
    """匯出案件為 CSV（含最新 client 屬性快照，套用當前篩選條件）。"""
    from app.core.enums import CaseStatus

    # ── 1. 查詢案件 + MAC 資訊（與 list_cases 相同篩選邏輯）──
    stmt = (
        select(
            Case,
            MaintenanceMacList.ip_address,
            MaintenanceMacList.description.label("client_desc"),
            MaintenanceMacList.tenant_group,
        )
        .outerjoin(MaintenanceMacList, Case.client_id == MaintenanceMacList.id)
        .where(Case.maintenance_id == maintenance_id)
    )

    if status:
        try:
            stmt = stmt.where(Case.status == CaseStatus(status))
        except ValueError:
            pass
    elif not include_resolved:
        stmt = stmt.where(Case.status.notin_([
            CaseStatus.RESOLVED, CaseStatus.IGNORED,
        ]))

    if assignee:
        stmt = stmt.where(Case.assignee == assignee)

    if ping_reachable is not None:
        if ping_reachable:
            stmt = stmt.where(Case.last_ping_reachable == True)  # noqa: E712
        else:
            stmt = stmt.where(
                or_(
                    Case.last_ping_reachable == False,  # noqa: E712
                    Case.last_ping_reachable == None,  # noqa: E711
                )
            )

    if search:
        keywords = search.strip().split()
        if keywords:
            search_conditions = []
            for field in [Case.mac_address, MaintenanceMacList.ip_address, MaintenanceMacList.description]:
                field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
                search_conditions.append(field_match)
            stmt = stmt.where(or_(*search_conditions))

    stmt = stmt.order_by(
        sql_case(
            (Case.last_ping_reachable == None, 0),   # noqa: E711
            (Case.last_ping_reachable == False, 1),   # noqa: E712
            else_=2,
        ),
        Case.mac_address,
    )

    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(_csv_header())
        output.seek(0)
        content = "\ufeff" + output.getvalue()
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{maintenance_id}_cases.csv"'
                ),
            },
        )

    # ── 2. 批量取每個案件的最新 ClientRecord 快照 ──
    client_ids = [case_obj.client_id for case_obj, *_ in rows if case_obj.client_id]

    snapshot_map: dict[int, ClientRecord] = {}
    if client_ids:
        lcr_stmt = (
            select(LatestClientRecord.client_id, LatestClientRecord.collected_at)
            .where(
                LatestClientRecord.maintenance_id == maintenance_id,
                LatestClientRecord.client_id.in_(client_ids),
            )
        )
        lcr_result = await session.execute(lcr_stmt)
        lcr_map = {r.client_id: r.collected_at for r in lcr_result.all()}

        if lcr_map:
            cr_stmt = (
                select(ClientRecord)
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.client_id.in_(list(lcr_map.keys())),
                )
                .order_by(ClientRecord.collected_at.desc())
            )
            cr_result = await session.execute(cr_stmt)
            for cr in cr_result.scalars().all():
                if cr.client_id not in snapshot_map:
                    snapshot_map[cr.client_id] = cr

    # ── 3. 生成 CSV ──
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_csv_header())

    for case_obj, ip_address, description, tenant_group in rows:
        snap = snapshot_map.get(case_obj.client_id)
        flags = case_obj.change_flags or {}

        acl_str = ""
        if snap and snap.acl_rules_applied:
            acl_raw = snap.acl_rules_applied
            if isinstance(acl_raw, list):
                acl_str = ", ".join(str(a) for a in acl_raw)
            elif isinstance(acl_raw, dict):
                acl_str = json.dumps(acl_raw, ensure_ascii=False)
            else:
                acl_str = str(acl_raw)

        changed_attrs = [
            ATTRIBUTE_LABELS.get(attr, attr)
            for attr in TRACKED_ATTRIBUTES
            if flags.get(attr)
        ]

        writer.writerow([
            case_obj.id,
            case_obj.mac_address,
            ip_address or "",
            description or "",
            tenant_group.value if tenant_group else "",
            case_obj.status.value if case_obj.status else "",
            case_obj.assignee or "",
            case_obj.summary or "",
            "是" if case_obj.last_ping_reachable else (
                "否" if case_obj.last_ping_reachable is False else "未知"
            ),
            (snap.switch_hostname if snap else ""),
            (snap.interface_name if snap else ""),
            (snap.speed if snap else ""),
            (snap.duplex if snap else ""),
            (snap.link_status if snap else ""),
            (str(snap.vlan_id) if snap and snap.vlan_id is not None else ""),
            acl_str,
            ", ".join(changed_attrs) if changed_attrs else "",
            _to_local(case_obj.created_at),
            _to_local(case_obj.updated_at),
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{maintenance_id}_cases.csv"'
            ),
        },
    )


@router.get("/{maintenance_id}/{case_id}")
async def get_case_detail(
    maintenance_id: str,
    case_id: int,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """取得案件詳情（含變化標籤和筆記）。"""
    detail = await _svc.get_case_detail(case_id, maintenance_id, session)
    if not detail:
        raise HTTPException(status_code=404, detail="找不到指定的案件")
    return {"success": True, "case": detail}


@router.put("/{maintenance_id}/{case_id}")
async def update_case(
    maintenance_id: str,
    case_id: int,
    data: CaseUpdateRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """更新案件（只有被指派人或 ROOT 可修改）。"""
    result = await _svc.update_case(
        case_id=case_id,
        maintenance_id=maintenance_id,
        user_display_name=user.get("display_name", ""),
        user_role=user.get("role", ""),
        session=session,
        summary=data.summary,
        status=data.status,
        assignee=data.assignee,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="找不到指定的案件")

    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])

    _task = asyncio.create_task(write_log(
        level="INFO",
        source="api",
        summary=f"更新案件 #{case_id}",
        module="cases",
        maintenance_id=maintenance_id,
    ))

    return {"success": True, "case": result}


@router.get("/{maintenance_id}/{case_id}/notes")
async def list_notes(
    maintenance_id: str,
    case_id: int,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """列出案件筆記。"""
    from sqlalchemy import select
    from app.db.models import CaseNote, Case

    # 驗證案件存在
    case_stmt = select(Case).where(
        Case.id == case_id,
        Case.maintenance_id == maintenance_id,
    )
    case = (await session.execute(case_stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="找不到指定的案件")

    notes_stmt = (
        select(CaseNote)
        .where(CaseNote.case_id == case_id)
        .order_by(CaseNote.created_at.desc())
    )
    result = await session.execute(notes_stmt)
    notes = [
        {
            "id": n.id,
            "author": n.author,
            "content": n.content,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in result.scalars().all()
    ]

    return {"success": True, "notes": notes}


@router.post("/{maintenance_id}/{case_id}/notes")
async def add_note(
    maintenance_id: str,
    case_id: int,
    data: CaseNoteCreateRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """新增案件筆記（任何登入使用者皆可新增，作為討論區）。"""
    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="筆記內容不可為空")

    result = await _svc.add_note(
        case_id=case_id,
        maintenance_id=maintenance_id,
        author=user.get("display_name", ""),
        user_role=user.get("role", ""),
        content=data.content,
        session=session,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="找不到指定的案件")

    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])

    await write_log(
        level="INFO",
        source=user.get("username", "unknown"),
        summary=f"新增案件 #{case_id} 筆記",
        module="cases",
        maintenance_id=maintenance_id,
    )

    return {"success": True, "note": result}


@router.put("/{maintenance_id}/{case_id}/notes/{note_id}")
async def update_note(
    maintenance_id: str,
    case_id: int,
    note_id: int,
    data: CaseNoteUpdateRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """修改案件筆記（只有原作者可修改）。"""
    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="筆記內容不可為空")

    result = await _svc.update_note(
        note_id=note_id,
        case_id=case_id,
        user_display_name=user.get("display_name", ""),
        user_role=user.get("role", ""),
        content=data.content,
        session=session,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="找不到指定的筆記")

    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])

    await write_log(
        level="INFO",
        source=user.get("username", "unknown"),
        summary=f"更新案件 #{case_id} 筆記",
        module="cases",
        maintenance_id=maintenance_id,
    )

    return {"success": True, "note": result}


@router.delete("/{maintenance_id}/{case_id}/notes/{note_id}")
async def delete_note(
    maintenance_id: str,
    case_id: int,
    note_id: int,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """刪除案件筆記（只有原作者可刪除）。"""
    result = await _svc.delete_note(
        note_id=note_id,
        case_id=case_id,
        user_display_name=user.get("display_name", ""),
        user_role=user.get("role", ""),
        session=session,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="找不到指定的筆記")

    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])

    await write_log(
        level="WARNING",
        source=user.get("username", "unknown"),
        summary=f"刪除案件 #{case_id} 筆記",
        module="cases",
        maintenance_id=maintenance_id,
    )

    return {"success": True}


@router.get("/{maintenance_id}/{case_id}/changes/{attribute}")
async def get_change_timeline(
    maintenance_id: str,
    case_id: int,
    attribute: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """取得某屬性的變化時間線。"""
    from sqlalchemy import select
    from app.db.models import Case, LatestClientRecord
    from app.services.case_service import TRACKED_ATTRIBUTES, ATTRIBUTE_LABELS

    if attribute not in TRACKED_ATTRIBUTES:
        raise HTTPException(status_code=400, detail=f"不支援的屬性: {attribute}")

    # 取得 Case
    case_stmt = select(Case).where(
        Case.id == case_id,
        Case.maintenance_id == maintenance_id,
    )
    case = (await session.execute(case_stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="找不到指定的案件")

    timeline = await _svc.get_change_timeline(
        maintenance_id=maintenance_id,
        client_id=case.client_id,
        attribute=attribute,
        session=session,
    )

    # 查詢最後確認時間
    lcr_stmt = select(LatestClientRecord).where(
        LatestClientRecord.maintenance_id == maintenance_id,
        LatestClientRecord.client_id == case.client_id,
    )
    lcr = (await session.execute(lcr_stmt)).scalar_one_or_none()

    return {
        "success": True,
        "attribute": attribute,
        "label": ATTRIBUTE_LABELS.get(attribute, attribute),
        "timeline": timeline,
        "last_checked_at": (
            lcr.last_checked_at.isoformat() if lcr and lcr.last_checked_at else None
        ),
    }


# ── helpers ──────────────────────────────────────────────────


def _to_local(dt) -> str:
    """UTC datetime → 設定時區的字串。"""
    if not dt:
        return ""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings.timezone)
    utc_dt = dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _csv_header() -> list[str]:
    """案件 CSV 標題列。"""
    return [
        "案件編號", "MAC", "IP", "備註", "租戶群組",
        "狀態", "負責人", "摘要", "Ping",
        "交換機", "介面", "速率", "雙工", "連線狀態", "VLAN", "ACL",
        "屬性變化", "建立時間", "更新時間",
    ]
