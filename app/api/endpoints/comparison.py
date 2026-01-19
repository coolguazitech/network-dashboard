"""
Client comparison endpoints.

提供客戶端比較相關的 API 端點。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.client_comparison import ClientComparisonService

router = APIRouter(prefix="/api/comparison", tags=["comparison"])
comparison_service = ClientComparisonService()


@router.post("/evaluate/{maintenance_id}")
async def evaluate_comparison(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    評估指定歲修 ID 的客戶端比較。
    
    Args:
        maintenance_id: 歲修 ID
        session: 資料庫會話
        
    Returns:
        評估結果
    """
    result = await comparison_service.evaluate_comparison(
        maintenance_id=maintenance_id,
        session=session,
    )
    return result


@router.get("/summary/{maintenance_id}")
async def get_summary(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    取得客戶端比較摘要。
    
    Args:
        maintenance_id: 歲修 ID
        session: 資料庫會話
        
    Returns:
        摘要數據
    """
    return await comparison_service.get_comparison_summary(
        maintenance_id=maintenance_id,
        session=session,
    )


@router.get("/details/{maintenance_id}")
async def get_details(
    maintenance_id: str,
    severity: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """
    取得詳細的客戶端比較結果。
    
    Args:
        maintenance_id: 歲修 ID
        severity: 嚴重程度過濾 (critical, warning, info)
        limit: 限制數量
        offset: 偏移量
        session: 資料庫會話
        
    Returns:
        比較結果列表
    """
    return await comparison_service.get_comparison_details(
        maintenance_id=maintenance_id,
        session=session,
        severity_filter=severity,
        limit=limit,
        offset=offset,
    )


@router.get("/client/{maintenance_id}/{mac_address}")
async def get_client_comparison(
    maintenance_id: str,
    mac_address: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict | None:
    """
    取得單個客戶端的比較結果。
    
    Args:
        maintenance_id: 歲修 ID
        mac_address: MAC 地址
        session: 資料庫會話
        
    Returns:
        比較結果或 None
    """
    return await comparison_service.get_client_comparison(
        maintenance_id=maintenance_id,
        mac_address=mac_address,
        session=session,
    )


@router.get("/affected-fields/{maintenance_id}")
async def get_affected_fields(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    取得受影響欄位的摘要統計。
    
    Args:
        maintenance_id: 歲修 ID
        session: 資料庫會話
        
    Returns:
        欄位變化統計
    """
    return await comparison_service.get_affected_fields_summary(
        maintenance_id=maintenance_id,
        session=session,
    )
