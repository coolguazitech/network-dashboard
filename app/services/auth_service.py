"""
Authentication Service.

處理密碼雜湊、JWT token 生成與驗證。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import bcrypt
import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import UserRole
from app.core.timezone import now_utc
from app.db.base import get_session_context
from app.db.models import User
from app.services.system_log import write_log

logger = logging.getLogger(__name__)

# JWT 設定（從 settings 讀取）
JWT_ALGORITHM = "HS256"


class AuthService:
    """認證服務。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """將密碼雜湊。"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """驗證密碼。"""
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )

    @staticmethod
    def create_token(user: User) -> str:
        """
        建立 JWT token。

        Token 內容包含：
        - user_id: 使用者 ID
        - username: 使用者名稱
        - role: 使用者角色
        - maintenance_id: 所屬歲修 ID
        - exp: 過期時間
        """
        expire = now_utc() + timedelta(hours=settings.jwt_expire_hours)
        payload = {
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role": user.role.value,
            "maintenance_id": user.maintenance_id,
            "is_root": user.role == UserRole.ROOT,  # 向後相容
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict[str, Any] | None:
        """
        解碼 JWT token。

        回傳 token payload 或 None（若 token 無效或過期）。
        """
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    async def authenticate(
        username: str, password: str
    ) -> tuple[User | None, str | None, str | None]:
        """
        驗證使用者。

        回傳 (user, token, error_message) 或 (None, None, error_message)。
        """
        async with get_session_context() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning("登入失敗: 帳號不存在 username=%s", username)
                await write_log(
                    level="WARNING", source="auth",
                    summary=f"登入失敗: 帳號不存在 ({username})",
                    module="auth",
                )
                return None, None, "帳號或密碼錯誤"

            if not AuthService.verify_password(password, user.password_hash):
                logger.warning("登入失敗: 密碼錯誤 username=%s", username)
                await write_log(
                    level="WARNING", source="auth",
                    summary=f"登入失敗: 密碼錯誤 ({username})",
                    module="auth",
                )
                return None, None, "帳號或密碼錯誤"

            # 檢查帳號是否啟用
            if not user.is_active:
                logger.warning("登入失敗: 帳號未啟用 username=%s", username)
                await write_log(
                    level="WARNING", source="auth",
                    summary=f"登入失敗: 帳號未啟用 ({username})",
                    module="auth",
                )
                return None, None, "帳號尚未啟用，請聯繫管理員"

            # 更新最後登入時間
            user.last_login_at = now_utc()
            await session.commit()

            # 建立 token
            token = AuthService.create_token(user)

            logger.info(
                "登入成功: username=%s role=%s",
                username, user.role.value,
            )
            await write_log(
                level="INFO", source="auth",
                summary=f"使用者登入: {user.display_name or username} ({user.role.value})",
                module="auth",
            )

            return user, token, None

    @staticmethod
    async def get_user_by_id(user_id: int) -> User | None:
        """根據 ID 取得使用者。"""
        async with get_session_context() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def change_password(
        user_id: int,
        old_password: str,
        new_password: str,
    ) -> bool:
        """
        變更密碼。

        驗證舊密碼後才能變更。
        """
        async with get_session_context() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return False

            if not AuthService.verify_password(old_password, user.password_hash):
                logger.warning("變更密碼失敗: 舊密碼錯誤 user_id=%d", user_id)
                return False

            user.password_hash = AuthService.hash_password(new_password)
            await session.commit()
            logger.info("密碼已變更 user_id=%d username=%s", user_id, user.username)
            await write_log(
                level="INFO", source="auth",
                summary=f"密碼已變更: {user.display_name or user.username}",
                module="auth",
            )
            return True

    @staticmethod
    async def create_root_if_not_exists(
        username: str = "root",
        password: str = "admin123",
    ) -> User | None:
        """
        建立預設 root 帳號（若不存在）。

        供初始化或 CLI 使用。
        """
        async with get_session_context() as session:
            # 檢查是否已有 root
            stmt = select(User).where(User.role == UserRole.ROOT)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                logger.info("Root 帳號已存在，跳過建立")
                return existing

            # 建立 root
            logger.info("建立預設 Root 帳號 username=%s", username)
            root = User(
                username=username,
                password_hash=AuthService.hash_password(password),
                display_name="系統管理員",
                role=UserRole.ROOT,
                maintenance_id=None,  # ROOT 不需要歲修 ID
                is_active=True,
            )
            session.add(root)
            await session.commit()
            await session.refresh(root)
            await write_log(
                level="INFO", source="system",
                summary="Root 帳號已建立",
                module="auth",
            )
            return root

    @staticmethod
    async def register_guest(
        username: str,
        password: str,
        maintenance_id: str,
        display_name: str | None = None,
        email: str | None = None,
    ) -> tuple[User | None, str | None]:
        """
        訪客自行註冊帳號。

        建立後帳號為未啟用狀態，需管理員手動啟用。
        回傳 (user, error_message)。
        """
        async with get_session_context() as session:
            # 檢查使用者名稱是否已存在
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning("Guest 註冊失敗: 使用者名稱已存在 username=%s", username)
                return None, "使用者名稱已存在"

            # 檢查顯示名稱是否重複
            effective_display_name = (display_name or "").strip() or username
            stmt = select(User).where(User.display_name == effective_display_name)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return None, f"顯示名稱「{effective_display_name}」已被使用"

            # 檢查歲修 ID 是否存在
            from app.db.models import MaintenanceConfig
            stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            maintenance = result.scalar_one_or_none()

            if not maintenance:
                return None, "歲修 ID 不存在"

            # 建立 Guest 帳號（未啟用）
            guest = User(
                username=username,
                password_hash=AuthService.hash_password(password),
                display_name=effective_display_name,
                email=email,
                role=UserRole.GUEST,
                maintenance_id=maintenance_id,
                is_active=False,  # 需等待啟用
            )
            session.add(guest)
            await session.commit()
            await session.refresh(guest)
            logger.info(
                "Guest 註冊成功: username=%s maintenance_id=%s",
                username, maintenance_id,
            )
            await write_log(
                level="INFO", source="auth",
                summary=f"Guest 註冊: {effective_display_name} ({maintenance_id})",
                module="auth",
                maintenance_id=maintenance_id,
            )
            return guest, None
