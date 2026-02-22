"""
Cases API endpoints.

案件管理 API 端點：查詢、更新、筆記、變化時間線。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.api.endpoints.auth import get_current_user, require_write
from app.services.case_service import CaseService
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

    await write_log(
        level="INFO",
        source="api",
        summary=f"更新案件 #{case_id}",
        module="cases",
        maintenance_id=maintenance_id,
    )

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
    from app.db.models import Case
    from app.services.case_service import TRACKED_ATTRIBUTES, ATTRIBUTE_LABELS

    if attribute not in TRACKED_ATTRIBUTES:
        raise HTTPException(status_code=400, detail=f"不支援的屬性: {attribute}")

    # 取得 Case 的 MAC
    case_stmt = select(Case).where(
        Case.id == case_id,
        Case.maintenance_id == maintenance_id,
    )
    case = (await session.execute(case_stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="找不到指定的案件")

    timeline = await _svc.get_change_timeline(
        maintenance_id=maintenance_id,
        mac_address=case.mac_address,
        attribute=attribute,
        session=session,
    )

    return {
        "success": True,
        "attribute": attribute,
        "label": ATTRIBUTE_LABELS.get(attribute, attribute),
        "timeline": timeline,
    }
