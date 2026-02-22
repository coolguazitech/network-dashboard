"""
Indicator API endpoints.
"""
from datetime import datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import get_current_user, require_write
from app.core.enums import DataType, IndicatorObjectType
from app.core.timezone import now_utc
from app.db.base import get_async_session
from app.services.indicator_service import IndicatorService
from app.services.system_log import write_log
from app.services.threshold_service import ensure_cache


# ── Pydantic Schemas ─────────────────────────────────────────────


class ObservedFieldSchema(BaseModel):
    """被觀測欄位的 schema。"""
    name: str = Field(..., description="欄位名稱")
    display_name: str = Field(..., description="顯示名稱")
    metric_name: str = Field(..., description="使用的 Metric 名稱")
    unit: str = Field(default="", description="單位")


class DisplayConfigSchema(BaseModel):
    """前端顯示設定 schema。"""
    chart_type: str = Field(default="line", description="圖表類型")
    x_axis_label: str = Field(default="時間")
    y_axis_label: str = Field(default="Pass Rate (%)")
    y_axis_min: float = Field(default=0.0)
    y_axis_max: float = Field(default=100.0)
    line_colors: list[str] = Field(
        default_factory=lambda: ["#5470c6", "#91cc75"]
    )
    show_raw_data_table: bool = Field(default=True)
    refresh_interval_seconds: int = Field(default=60)


class IndicatorMetadataResponse(BaseModel):
    """Indicator 元資料回應。"""
    name: str = Field(..., description="Indicator 唯一識別名稱")
    title: str = Field(..., description="顯示標題")
    description: str = Field(..., description="描述")
    object_type: IndicatorObjectType = Field(
        ...,
        description="觀測的最小單位類型"
    )
    data_type: DataType = Field(..., description="資料類型")
    observed_fields: list[ObservedFieldSchema] = Field(
        ...,
        description="被觀測的欄位列表"
    )
    display_config: DisplayConfigSchema = Field(
        ...,
        description="前端顯示設定"
    )


class TimeSeriesPointSchema(BaseModel):
    """時間序列資料點。"""
    timestamp: datetime = Field(..., description="時間戳記")
    values: dict[str, float] = Field(
        ...,
        description="欄位名稱到數值的映射"
    )


class TimeSeriesResponse(BaseModel):
    """時間序列資料回應（用於前端圖表）。"""
    indicator_name: str = Field(..., description="Indicator 名稱")
    title: str = Field(..., description="圖表標題")
    series_names: list[str] = Field(
        ...,
        description="折線名稱列表"
    )
    data: list[TimeSeriesPointSchema] = Field(
        ...,
        description="時間序列資料"
    )
    display_config: DisplayConfigSchema = Field(
        ...,
        description="顯示設定"
    )
    last_updated: Optional[datetime] = Field(
        None,
        description="最後更新時間"
    )


class TableColumnSchema(BaseModel):
    """表格欄位定義。"""
    key: str = Field(..., description="欄位識別鍵")
    title: str = Field(..., description="欄位標題")
    data_type: str = Field(default="string", description="資料類型")
    sortable: bool = Field(default=True)
    width: Optional[int] = Field(None, description="欄位寬度")


class RawDataTableResponse(BaseModel):
    """原始資料表格回應。"""
    indicator_name: str = Field(..., description="Indicator 名稱")
    title: str = Field(..., description="表格標題")
    columns: list[TableColumnSchema] = Field(
        ...,
        description="欄位定義"
    )
    rows: list[dict[str, Any]] = Field(
        ...,
        description="資料列"
    )
    total: int = Field(..., description="總資料筆數")
    page: int = Field(default=1)
    page_size: int = Field(default=50)
    last_updated: Optional[datetime] = None


class IndicatorSummary(BaseModel):
    """Indicator 摘要資訊（用於 Dashboard 總覽）。"""
    name: str
    title: str
    current_pass_rates: dict[str, float] = Field(
        ...,
        description="各欄位當前的 pass rate"
    )
    trend: str = Field(
        default="stable",
        description="趨勢: up, down, stable"
    )
    last_updated: Optional[datetime] = None


class DashboardResponse(BaseModel):
    """Dashboard 總覽回應。"""
    indicators: list[IndicatorSummary] = Field(
        ...,
        description="所有 Indicator 摘要"
    )
    total_switches: int = Field(default=0)
    active_switches: int = Field(default=0)
    total_interfaces: int = Field(default=0)
    last_collection_time: Optional[datetime] = None


class CollectionTriggerRequest(BaseModel):
    """觸發資料收集請求。"""
    indicator_names: Optional[list[str]] = Field(
        None,
        description="要收集的 Indicator 名稱列表，None 表示全部"
    )
    switch_hostnames: Optional[list[str]] = Field(
        None,
        description="要收集的 Switch 列表，None 表示全部"
    )


class CollectionStatusResponse(BaseModel):
    """資料收集狀態回應。"""
    collection_id: int
    indicator_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_items: int = 0
    success_items: int = 0
    failed_items: int = 0
    error_message: Optional[str] = None


# ── Router ───────────────────────────────────────────────────────

router = APIRouter()

indicator_manager = IndicatorService()


@router.get("", response_model=list[IndicatorMetadataResponse])
async def list_indicators(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[IndicatorMetadataResponse]:
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
async def get_indicator(
    indicator_name: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> IndicatorMetadataResponse:
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


@router.get("/{maintenance_id}/{indicator_name}/timeseries", response_model=TimeSeriesResponse)
async def get_indicator_timeseries(
    maintenance_id: str,
    indicator_name: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    limit: int = Query(100, ge=1, le=1000, description="資料點數量限制"),
    session: AsyncSession = Depends(get_async_session),
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

    await ensure_cache(session, maintenance_id)
    time_series = await indicator.get_time_series(
        limit=limit,
        session=session,
        maintenance_id=maintenance_id,
    )
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
            **{
                k: v
                for k, v in metadata.display_config.model_dump().items()
                if v is not None
            }
        ),
        last_updated=getattr(indicator, "_last_collection_time", None),
    )


@router.get("/{maintenance_id}/{indicator_name}/rawdata", response_model=RawDataTableResponse)
async def get_indicator_raw_data(
    maintenance_id: str,
    indicator_name: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
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

    await ensure_cache(session, maintenance_id)
    raw_data = await indicator.get_latest_raw_data(
        limit=page_size * page,
        session=session,
        maintenance_id=maintenance_id,
    )
    metadata = indicator.get_metadata()

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_data = raw_data[start_idx:end_idx]

    columns = _get_columns_for_indicator(indicator_name)
    rows = [data.model_dump() for data in paged_data]

    return RawDataTableResponse(
        indicator_name=indicator_name,
        title=f"{metadata.title} - 原始資料",
        columns=columns,
        rows=rows,
        total=len(raw_data),
        page=page,
        page_size=page_size,
        last_updated=getattr(indicator, "_last_collection_time", None),
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

    return [
        TableColumnSchema(key="id", title="ID"),
        TableColumnSchema(key="value", title="Value"),
        TableColumnSchema(key="pass", title="Pass"),
        TableColumnSchema(key="collected_at", title="Time"),
    ]


@router.post("/{maintenance_id}/{indicator_name}/collect", response_model=CollectionStatusResponse)
async def trigger_collection(
    maintenance_id: str,
    indicator_name: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

    await write_log(
        level="INFO",
        source=_user.get("username", "unknown"),
        summary=f"手動觸發資料收集: {indicator_name}",
        module="indicators",
        maintenance_id=maintenance_id,
    )

    return CollectionStatusResponse(
        collection_id=1,
        indicator_name=indicator_name,
        status="pending",
        started_at=now_utc(),
        total_items=0,
        success_items=0,
        failed_items=0,
    )
