"""
Authentication API endpoints.

提供登入、登出、取得當前使用者資訊等功能。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.services.auth_service import AuthService
from app.services.system_log import write_log
from app.db.base import get_async_session
from app.db.models import MaintenanceConfig

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


# ══════════════════════════════════════════════════════════════════
# Request/Response Models
# ══════════════════════════════════════════════════════════════════


class LoginRequest(BaseModel):
    """登入請求。"""

    username: str
    password: str


class LoginResponse(BaseModel):
    """登入回應。"""

    token: str
    user: dict[str, Any]


class ChangePasswordRequest(BaseModel):
    """變更密碼請求。"""

    old_password: str
    new_password: str


class GuestRegisterRequest(BaseModel):
    """Guest 註冊請求。"""

    username: str
    password: str
    maintenance_id: str
    display_name: str | None = None
    email: str | None = None


class UserResponse(BaseModel):
    """使用者資訊回應。"""

    id: int
    username: str
    display_name: str | None
    email: str | None
    role: str
    maintenance_id: str | None
    is_root: bool  # 向後相容


# ══════════════════════════════════════════════════════════════════
# Dependencies
# ══════════════════════════════════════════════════════════════════


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> dict[str, Any]:
    """
    從 JWT token 取得當前使用者。

    用於需要登入的 API。
    會驗證使用者是否仍存在於資料庫中。
    """
    token = credentials.credentials
    payload = AuthService.decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 無效或已過期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 驗證使用者是否仍存在（可能已被刪除）
    user_id = payload.get("user_id")
    if user_id:
        user = await AuthService.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="使用者已不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return payload


def require_write():
    """
    檢查使用者是否有寫入權限。

    ROOT 和 PM 有寫入權限，GUEST 沒有。
    """
    async def check_write(
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ):
        role = user.get("role")
        if role not in [UserRole.ROOT.value, UserRole.PM.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您沒有寫入權限",
            )
        return user

    return check_write


async def require_root(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    """檢查是否為 root 使用者。"""
    if user.get("role") != UserRole.ROOT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此操作需要管理員權限",
        )
    return user


def check_maintenance_access(user: dict[str, Any], maintenance_id: str) -> None:
    """
    檢查使用者是否有權訪問指定的歲修。

    權限規則：
    - ROOT: 可訪問所有歲修
    - PM/GUEST: 只能訪問被指派的歲修

    Args:
        user: JWT payload 中的使用者資訊
        maintenance_id: 要訪問的歲修 ID

    Raises:
        HTTPException: 若使用者無權訪問該歲修
    """
    user_role = user.get("role")
    user_maintenance_id = user.get("maintenance_id")

    # ROOT 可以訪問所有歲修
    if user_role == UserRole.ROOT.value:
        return

    # 非 ROOT 使用者必須被指派該歲修才能訪問
    if user_maintenance_id != maintenance_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您沒有權限訪問此歲修",
        )


# ══════════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════════


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest) -> dict[str, Any]:
    """
    使用者登入。

    驗證帳號密碼後回傳 JWT token。
    """
    user, token, error = await AuthService.authenticate(data.username, data.password)

    if not user or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error or "帳號或密碼錯誤",
        )

    await write_log(
        level="INFO",
        source=user.username,
        summary=f"使用者「{user.display_name or user.username}」登入",
        module="auth",
        maintenance_id=user.maintenance_id,
    )

    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "email": user.email,
            "role": user.role.value,
            "maintenance_id": user.maintenance_id,
            "is_root": user.role == UserRole.ROOT,
        },
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """取得當前登入使用者資訊。"""
    db_user = await AuthService.get_user_by_id(user["user_id"])
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="使用者不存在",
        )

    return {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name or db_user.username,
        "email": db_user.email,
        "role": db_user.role.value,
        "maintenance_id": db_user.maintenance_id,
        "is_root": db_user.role == UserRole.ROOT,
    }


@router.put("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, str]:
    """變更當前使用者密碼。"""
    success = await AuthService.change_password(
        user["user_id"],
        data.old_password,
        data.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="舊密碼錯誤",
        )

    await write_log(
        level="INFO",
        source=user.get("username", "unknown"),
        summary=f"使用者「{user.get('username', '')}」變更密碼",
        module="auth",
    )

    return {"message": "密碼變更成功"}


@router.post("/register-guest")
async def register_guest(data: GuestRegisterRequest) -> dict[str, Any]:
    """
    訪客自行註冊帳號。

    註冊後帳號為未啟用狀態，需聯繫管理員啟用。
    """
    user, error = await AuthService.register_guest(
        username=data.username,
        password=data.password,
        maintenance_id=data.maintenance_id,
        display_name=data.display_name,
        email=data.email,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "註冊失敗",
        )

    await write_log(
        level="INFO",
        source=user.username,
        summary=f"訪客「{user.display_name or user.username}」自行註冊（待啟用）",
        module="auth",
        maintenance_id=user.maintenance_id,
    )

    return {
        "message": "註冊成功，請聯繫管理員啟用帳號",
        "username": user.username,
        "maintenance_id": user.maintenance_id,
    }


@router.post("/init-root")
async def init_root() -> dict[str, Any]:
    """
    初始化 root 帳號。

    若系統尚無 root 帳號，則建立預設 root (密碼: admin123)。
    建立後請立即變更密碼！
    """
    root = await AuthService.create_root_if_not_exists()

    if root:
        await write_log(
            level="INFO",
            source="system",
            summary="初始化 Root 帳號",
            module="auth",
        )
        return {
            "message": "Root 帳號已就緒",
            "username": root.username,
            "note": "若為新建立，預設密碼為 admin123，請立即變更！",
        }

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="無法建立 root 帳號",
    )


@router.get("/maintenances-public")
async def list_maintenances_public(
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, Any]]:
    """
    公開端點：取得可供註冊的歲修列表。

    此端點不需要認證，用於訪客註冊時選擇歲修。
    回傳所有歲修的基本資訊（id 和 name），不限定 is_active。
    """
    stmt = select(MaintenanceConfig).order_by(MaintenanceConfig.created_at.desc())
    result = await session.execute(stmt)
    configs = result.scalars().all()

    return [
        {
            "id": c.maintenance_id,
            "name": c.name or c.maintenance_id,
        }
        for c in configs
    ]
