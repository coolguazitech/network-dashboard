"""
Indicator API endpoints.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.schemas.indicator import (
    IndicatorMetadataResponse,
    TimeSeriesResponse,
    TimeSeriesPointSchema,
    RawDataTableResponse,
    TableColumnSchema,
    DisplayConfigSchema,
    ObservedFieldSchema,
    CollectionTriggerRequest,
    CollectionStatusResponse,
)
from app.indicators import TransceiverIndicator
from app.services.indicator_service import IndicatorService

router = APIRouter()

# 初始化 Indicator Manager（實際應用中會在應用啟動時初始化）
indicator_manager = IndicatorService()


@router.get("", response_model=list[IndicatorMetadataResponse])
async def list_indicators() -> list[IndicatorMetadataResponse]:
    """
    取得所有可用的 Indicator 列表。
    """
    indicators = indicator_manager.get_all_indicators()
    result = []
    
    for indicator in indicators:
        metadata = indicator.get_metadata()
        result.append(
            IndicatorMetadataResponse(
                name=metadata.name,
                title=metadata.title,
                description=metadata.description,
                object_type=metadata.object_type,
                data_type=metadata.data_type,
                observed_fields=[
                    ObservedFieldSchema(
                        name=f.name,
                        display_name=f.display_name,
                        metric_name=f.metric_name,
                        unit=f.unit,
                    )
                    for f in metadata.observed_fields
                ],
                display_config=DisplayConfigSchema(
                    chart_type=metadata.display_config.chart_type,
                    x_axis_label=metadata.display_config.x_axis_label,
                    y_axis_label=metadata.display_config.y_axis_label,
                    y_axis_min=metadata.display_config.y_axis_min,
                    y_axis_max=metadata.display_config.y_axis_max,
                    line_colors=metadata.display_config.line_colors,
                    show_raw_data_table=metadata.display_config.show_raw_data_table,
                    refresh_interval_seconds=metadata.display_config.refresh_interval_seconds,
                ),
            )
        )
    
    return result


@router.get("/{indicator_name}", response_model=IndicatorMetadataResponse)
async def get_indicator(indicator_name: str) -> IndicatorMetadataResponse:
    """
    取得指定 Indicator 的元資料。
    """
    indicator = indicator_manager.get_indicator(indicator_name)
    
    if not indicator:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator '{indicator_name}' not found"
        )
    
    metadata = indicator.get_metadata()
    return IndicatorMetadataResponse(
        name=metadata.name,
        title=metadata.title,
        description=metadata.description,
        object_type=metadata.object_type,
        data_type=metadata.data_type,
        observed_fields=[
            ObservedFieldSchema(
                name=f.name,
                display_name=f.display_name,
                metric_name=f.metric_name,
                unit=f.unit,
            )
            for f in metadata.observed_fields
        ],
        display_config=DisplayConfigSchema(
            chart_type=metadata.display_config.chart_type,
            x_axis_label=metadata.display_config.x_axis_label,
            y_axis_label=metadata.display_config.y_axis_label,
            y_axis_min=metadata.display_config.y_axis_min,
            y_axis_max=metadata.display_config.y_axis_max,
            line_colors=metadata.display_config.line_colors,
            show_raw_data_table=metadata.display_config.show_raw_data_table,
            refresh_interval_seconds=metadata.display_config.refresh_interval_seconds,
        ),
    )


@router.get("/{indicator_name}/timeseries", response_model=TimeSeriesResponse)
async def get_indicator_timeseries(
    indicator_name: str,
    limit: int = Query(100, ge=1, le=1000, description="資料點數量限制"),
) -> TimeSeriesResponse:
    """
    取得 Indicator 的時間序列資料（用於前端圖表）。
    """
    indicator = indicator_manager.get_indicator(indicator_name)
    
    if not indicator:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator '{indicator_name}' not found"
        )
    
    time_series = indicator.get_time_series(limit=limit)
    metadata = indicator.get_metadata()
    
    return TimeSeriesResponse(
        indicator_name=indicator_name,
        title=metadata.title,
        series_names=[f.name for f in metadata.observed_fields],
        data=[
            TimeSeriesPointSchema(
                timestamp=point.timestamp,
                values=point.values,
            )
            for point in time_series
        ],
        display_config=DisplayConfigSchema(
            chart_type=metadata.display_config.chart_type,
            x_axis_label=metadata.display_config.x_axis_label,
            y_axis_label=metadata.display_config.y_axis_label,
            y_axis_min=metadata.display_config.y_axis_min,
            y_axis_max=metadata.display_config.y_axis_max,
            line_colors=metadata.display_config.line_colors,
        ),
        last_updated=indicator._last_collection_time,
    )


@router.get("/{indicator_name}/rawdata", response_model=RawDataTableResponse)
async def get_indicator_raw_data(
    indicator_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> RawDataTableResponse:
    """
    取得 Indicator 的原始資料表格。
    """
    indicator = indicator_manager.get_indicator(indicator_name)
    
    if not indicator:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator '{indicator_name}' not found"
        )
    
    # 取得原始資料
    raw_data = indicator.get_latest_raw_data(limit=page_size * page)
    metadata = indicator.get_metadata()
    
    # 分頁
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_data = raw_data[start_idx:end_idx]
    
    # 建立欄位定義
    columns = _get_columns_for_indicator(indicator_name)
    
    # 轉換資料為 dict
    rows = [data.model_dump() for data in paged_data]
    
    return RawDataTableResponse(
        indicator_name=indicator_name,
        title=f"{metadata.title} - 原始資料",
        columns=columns,
        rows=rows,
        total=len(raw_data),
        page=page,
        page_size=page_size,
        last_updated=indicator._last_collection_time,
    )


def _get_columns_for_indicator(indicator_name: str) -> list[TableColumnSchema]:
    """根據 Indicator 類型回傳對應的表格欄位定義。"""
    if indicator_name == "transceiver":
        return [
            TableColumnSchema(key="switch_hostname", title="Switch"),
            TableColumnSchema(key="interface_name", title="Interface"),
            TableColumnSchema(
                key="tx_power", title="Tx (dBm)", data_type="float"
            ),
            TableColumnSchema(
                key="rx_power", title="Rx (dBm)", data_type="float"
            ),
            TableColumnSchema(
                key="tx_pass", title="Tx Pass", data_type="boolean"
            ),
            TableColumnSchema(
                key="rx_pass", title="Rx Pass", data_type="boolean"
            ),
            TableColumnSchema(
                key="collected_at", title="收集時間", data_type="datetime"
            ),
        ]
    
    # 預設欄位
    return [
        TableColumnSchema(key="id", title="ID"),
        TableColumnSchema(key="value", title="Value"),
        TableColumnSchema(key="pass", title="Pass"),
        TableColumnSchema(key="collected_at", title="Time"),
    ]


@router.post("/{indicator_name}/collect", response_model=CollectionStatusResponse)
async def trigger_collection(
    indicator_name: str,
    request: Optional[CollectionTriggerRequest] = None,
    session: AsyncSession = Depends(get_async_session),
) -> CollectionStatusResponse:
    """
    觸發指定 Indicator 的資料收集。
    """
    indicator = indicator_manager.get_indicator(indicator_name)
    
    if not indicator:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator '{indicator_name}' not found"
        )
    
    # 這裡會觸發資料收集服務
    # 實際實作中會是非同步的背景任務
    from datetime import datetime
    
    # 模擬回應
    return CollectionStatusResponse(
        collection_id=1,
        indicator_name=indicator_name,
        status="pending",
        started_at=datetime.utcnow(),
        total_items=0,
        success_items=0,
        failed_items=0,
    )
