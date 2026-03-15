"""
資料保留與清理服務。

基準+變化點策略下，DB 資料量已大幅降低。
此服務只負責清理「已停用超過 N 天」的歲修資料。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, and_

from app.core.config import settings
from app.db.base import get_session_context
from app.db.models import (
    CollectionBatch,
    CollectionError,
    LatestCollectionBatch,
    MaintenanceConfig,
)

logger = logging.getLogger(__name__)


class RetentionService:
    """清理已停用超過 retention_days 的歲修採集資料。"""

    async def cleanup_deactivated(self) -> dict[str, int]:
        """
        刪除已停用超過 retention_days_after_deactivation 的歲修所有採集資料。

        Returns:
            dict: {maintenances_cleaned, batches_deleted, latest_deleted, errors_deleted}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=settings.retention_days_after_deactivation
        )

        stats = {
            "maintenances_cleaned": 0,
            "batches_deleted": 0,
            "latest_deleted": 0,
            "errors_deleted": 0,
        }

        async with get_session_context() as session:
            # 查出已停用且 updated_at 超過保留期限的歲修
            stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.is_active == False,  # noqa: E712
                MaintenanceConfig.updated_at <= cutoff,
            )
            result = await session.execute(stmt)
            expired_configs = result.scalars().all()

            if not expired_configs:
                return stats

            expired_ids = [c.maintenance_id for c in expired_configs]
            logger.info(
                "Retention cleanup: found %d deactivated maintenances to clean: %s",
                len(expired_ids), expired_ids,
            )

            # 刪除 LatestCollectionBatch
            r1 = await session.execute(
                delete(LatestCollectionBatch).where(
                    LatestCollectionBatch.maintenance_id.in_(expired_ids)
                )
            )
            stats["latest_deleted"] = r1.rowcount

            # 刪除 CollectionBatch（CASCADE 自動刪 typed records）
            r2 = await session.execute(
                delete(CollectionBatch).where(
                    CollectionBatch.maintenance_id.in_(expired_ids)
                )
            )
            stats["batches_deleted"] = r2.rowcount

            # 刪除 CollectionError
            r3 = await session.execute(
                delete(CollectionError).where(
                    CollectionError.maintenance_id.in_(expired_ids)
                )
            )
            stats["errors_deleted"] = r3.rowcount

            stats["maintenances_cleaned"] = len(expired_ids)

            await session.commit()

            logger.info(
                "Retention cleanup done: %d maintenances, "
                "%d batches, %d latest, %d errors deleted",
                stats["maintenances_cleaned"],
                stats["batches_deleted"],
                stats["latest_deleted"],
                stats["errors_deleted"],
            )

        return stats

    async def cleanup_old_batches(self, retention_days: int = 7) -> dict[str, int]:
        """
        清理活躍歲修中超過 retention_days 的非最新 batch。

        保留 latest_collection_batches 指向的 batch（目前使用中），
        刪除同 maintenance + collection_type 下超齡的舊 batch。
        CASCADE 會自動刪除對應的 typed records（ping_records 等）。

        Returns:
            dict: {batches_deleted}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        stats = {"batches_deleted": 0}

        async with get_session_context() as session:
            # 取得所有 latest batch_id（這些不能刪）
            latest_ids_subq = (
                select(LatestCollectionBatch.batch_id).subquery()
            )

            # 刪除：collected_at < cutoff 且不是 latest 的 batch
            stmt = delete(CollectionBatch).where(
                and_(
                    CollectionBatch.collected_at < cutoff,
                    CollectionBatch.id.notin_(select(latest_ids_subq.c.batch_id)),
                )
            )
            result = await session.execute(stmt)
            stats["batches_deleted"] = result.rowcount

            if stats["batches_deleted"] > 0:
                await session.commit()
                logger.info(
                    "Old batch cleanup: deleted %d batches older than %d days",
                    stats["batches_deleted"], retention_days,
                )

        return stats
