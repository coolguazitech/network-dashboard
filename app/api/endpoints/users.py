"""
User Management API endpoints.

提供使用者 CRUD 及角色管理功能（僅 root 可操作）。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.endpoints.auth import get_current_user, require_root
from app.core.enums import UserRole
from app.db.base import get_async_session
from app.db.models import User, MaintenanceConfig
from app.services.auth_service import AuthService
from app.services.system_log import write_log
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["Users"])


# ══════════════════════════════════════════════════════════════════
# Request/Response Models
# ══════════════════════════════════════════════════════════════════


class CreateUserRequest(BaseModel):
    """建立使用者請求。"""

    username: str
    password: str
    display_name: str
    email: str | None = None
    role: str = "guest"  # root, pm, guest
    maintenance_id: str | None = None  # PM/GUEST 必填


class UpdateUserRequest(BaseModel):
    """更新使用者請求。"""

    display_name: str | None = None
    email: str | None = None
    is_active: bool | None = None
    role: str | None = None  # root, pm, guest
    maintenance_id: str | None = None


class ResetPasswordRequest(BaseModel):
    """重設密碼請求。"""

    new_password: str


class UserListResponse(BaseModel):
    """使用者列表項目。"""

    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    maintenance_id: str | None
    is_active: bool
    last_login_at: str | None


class RoleItem(BaseModel):
    """角色項目。"""

    value: str
    label: str
    description: str


# ══════════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════════


@router.get("/display-names")
async def list_user_display_names(
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> list[str]:
    """
    回傳所有 active 使用者的 display_name（供指派 dropdown 用）。

    任何已登入使用者皆可存取。
    """
    stmt = (
        select(User.display_name)
        .where(User.is_active == True)  # noqa: E712
        .order_by(User.display_name)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall()]


@router.get("/roles/available")
async def get_available_roles(
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[RoleItem]:
    """
    取得所有可用角色列表。

    供前端顯示角色選項。
    """
    role_info = {
        UserRole.ROOT: ("管理員", "可管理歲修和使用者，擁有所有權限"),
        UserRole.PM: ("執秘", "有歲修內的所有寫入權限"),
        UserRole.GUEST: ("訪客", "只有讀取權限，無法進行任何寫入操作"),
    }

    return [
        RoleItem(
            value=role.value,
            label=role_info[role][0],
            description=role_info[role][1],
        )
        for role in UserRole
    ]


@router.get("")
async def list_users(
    _: Annotated[dict[str, Any], Depends(require_root)],
    maintenance_id: str | None = Query(None, description="篩選特定歲修的使用者"),
    include_inactive: bool = Query(True, description="是否包含未啟用帳號"),
    session: AsyncSession = Depends(get_async_session),
) -> list[UserListResponse]:
    """
    列出所有使用者（僅 root 可用）。
    """
    stmt = select(User).order_by(User.id)

    if maintenance_id:
        stmt = stmt.where(User.maintenance_id == maintenance_id)

    if not include_inactive:
        stmt = stmt.where(User.is_active == True)  # noqa: E712

    result = await session.execute(stmt)
    users = result.scalars().all()

    return [
        UserListResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role.value,
            maintenance_id=user.maintenance_id,
            is_active=user.is_active,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        )
        for user in users
    ]


@router.get("/pending")
async def list_pending_users(
    _: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> list[UserListResponse]:
    """
    列出待啟用的使用者（僅 root 可用）。

    這些是自行註冊但尚未被管理員啟用的 Guest 帳號。
    """
    stmt = (
        select(User)
        .where(User.is_active == False)  # noqa: E712
        .order_by(User.created_at.desc())
    )
    result = await session.execute(stmt)
    users = result.scalars().all()

    return [
        UserListResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role.value,
            maintenance_id=user.maintenance_id,
            is_active=user.is_active,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        )
        for user in users
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    data: CreateUserRequest,
    current_user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> UserListResponse:
    """
    建立新使用者（僅 root 可用）。
    """
    # 檢查顯示名稱
    if not data.display_name or not data.display_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="顯示名稱為必填欄位",
        )

    # 檢查使用者名稱是否已存在
    stmt = select(User).where(User.username == data.username)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"使用者名稱 '{data.username}' 已存在",
        )

    # 檢查顯示名稱是否已存在
    stmt = select(User).where(User.display_name == data.display_name.strip())
    result = await session.execute(stmt)
    existing_display = result.scalar_one_or_none()

    if existing_display:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"顯示名稱 '{data.display_name}' 已被使用",
        )

    # 驗證角色
    try:
        role = UserRole(data.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無效的角色: {data.role}",
        )

    # PM 和 GUEST 必須指定 maintenance_id
    if role in [UserRole.PM, UserRole.GUEST] and not data.maintenance_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="執秘和訪客必須指定歲修 ID",
        )

    # 每個歲修只能有一個執秘
    if role == UserRole.PM and data.maintenance_id:
        stmt = select(User).where(
            User.role == UserRole.PM,
            User.maintenance_id == data.maintenance_id,
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"歲修 '{data.maintenance_id}' 已有執秘，每個歲修只能有一位執秘",
            )

    # 驗證 maintenance_id 是否存在
    if data.maintenance_id:
        stmt = select(MaintenanceConfig).where(
            MaintenanceConfig.maintenance_id == data.maintenance_id
        )
        result = await session.execute(stmt)
        maintenance = result.scalar_one_or_none()
        if not maintenance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"歲修 ID '{data.maintenance_id}' 不存在",
            )

    # 建立使用者
    user = User(
        username=data.username,
        password_hash=AuthService.hash_password(data.password),
        display_name=data.display_name,
        email=data.email,
        role=role,
        maintenance_id=data.maintenance_id if role != UserRole.ROOT else None,
        is_active=True,  # 管理員建立的帳號直接啟用
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    await write_log(
        level="INFO",
        source=current_user.get("username", "unknown"),
        summary=f"新增使用者「{user.display_name}」(角色: {role.value})",
        module="users",
        maintenance_id=user.maintenance_id,
    )

    return UserListResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role.value,
        maintenance_id=user.maintenance_id,
        is_active=user.is_active,
        last_login_at=None,
    )


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    _: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> UserListResponse:
    """
    取得單一使用者資訊（僅 root 可用）。
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    return UserListResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role.value,
        maintenance_id=user.maintenance_id,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    data: UpdateUserRequest,
    current_user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> UserListResponse:
    """
    更新使用者資訊（僅 root 可用）。

    注意：不可停用 root 帳號或自己的帳號。
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    # 防止停用 root 或自己
    if data.is_active is False:
        if user.role == UserRole.ROOT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不可停用管理員帳號",
            )
        if user.id == current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不可停用自己的帳號",
            )

    # 防止更改自己的角色
    if data.role is not None and user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不可更改自己的角色",
        )

    # 更新欄位
    if data.display_name is not None:
        name = data.display_name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="顯示名稱不可為空",
            )
        # 檢查顯示名稱是否已被其他使用者使用
        stmt = select(User).where(User.display_name == name, User.id != user_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"顯示名稱 '{name}' 已被使用",
            )
        user.display_name = name
    if data.email is not None:
        user.email = data.email
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.role is not None:
        try:
            new_role = UserRole(data.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"無效的角色: {data.role}",
            )

        # 每個歲修只能有一個執秘
        mid = data.maintenance_id if data.maintenance_id is not None else user.maintenance_id
        if new_role == UserRole.PM and mid:
            stmt = select(User).where(
                User.role == UserRole.PM,
                User.maintenance_id == mid,
                User.id != user_id,
            )
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"歲修 '{mid}' 已有執秘，每個歲修只能有一位執秘",
                )

        user.role = new_role
    if data.maintenance_id is not None:
        # 驗證 maintenance_id 是否存在
        if data.maintenance_id:
            stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.maintenance_id == data.maintenance_id
            )
            result = await session.execute(stmt)
            maintenance = result.scalar_one_or_none()
            if not maintenance:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"歲修 ID '{data.maintenance_id}' 不存在",
                )
        user.maintenance_id = data.maintenance_id

    await session.commit()
    await session.refresh(user)

    await write_log(
        level="INFO",
        source=current_user.get("username", "unknown"),
        summary=f"更新使用者「{user.display_name}」",
        module="users",
        maintenance_id=user.maintenance_id,
    )

    return UserListResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role.value,
        maintenance_id=user.maintenance_id,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> UserListResponse:
    """
    啟用使用者帳號（僅 root 可用）。

    用於啟用 Guest 自行註冊的帳號。
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="帳號已經是啟用狀態",
        )

    user.is_active = True
    await session.commit()
    await session.refresh(user)

    await write_log(
        level="INFO",
        source=current_user.get("username", "unknown"),
        summary=f"啟用使用者「{user.display_name}」",
        module="users",
        maintenance_id=user.maintenance_id,
    )

    return UserListResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role.value,
        maintenance_id=user.maintenance_id,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    刪除使用者（僅 root 可用）。

    注意：不可刪除 root 帳號或自己。
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    if user.role == UserRole.ROOT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不可刪除管理員帳號",
        )

    if user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不可刪除自己的帳號",
        )

    # 保存資訊供日誌使用
    deleted_name = user.display_name
    deleted_mid = user.maintenance_id

    # 刪除使用者
    await session.delete(user)
    await session.commit()

    await write_log(
        level="WARNING",
        source=current_user.get("username", "unknown"),
        summary=f"刪除使用者「{deleted_name}」",
        module="users",
        maintenance_id=deleted_mid,
    )


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: ResetPasswordRequest,
    current_user: Annotated[dict[str, Any], Depends(require_root)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    """
    重設使用者密碼（僅 root 可用）。
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    user.password_hash = AuthService.hash_password(data.new_password)
    await session.commit()

    await write_log(
        level="WARNING",
        source=current_user.get("username", "unknown"),
        summary=f"重設使用者「{user.display_name}」的密碼",
        module="users",
        maintenance_id=user.maintenance_id,
    )

    return {"message": f"使用者 {user.username} 的密碼已重設"}
