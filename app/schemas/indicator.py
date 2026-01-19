"""
Pydantic schemas for Indicator API models.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.enums import IndicatorObjectType, DataType


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
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "transceiver",
                "title": "光模組監控",
                "description": "監控 Switch 介面的光模組 Tx/Rx 功率值",
                "object_type": "interface",
                "data_type": "float",
                "observed_fields": [
                    {
                        "name": "tx",
                        "display_name": "Tx 功率",
                        "metric_name": "tx",
                        "unit": "dBm"
                    },
                    {
                        "name": "rx",
                        "display_name": "Rx 功率",
                        "metric_name": "rx",
                        "unit": "dBm"
                    }
                ],
                "display_config": {
                    "chart_type": "line",
                    "x_axis_label": "時間",
                    "y_axis_label": "Pass Rate (%)"
                }
            }
        }


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
    
    class Config:
        json_schema_extra = {
            "example": {
                "indicator_name": "transceiver",
                "title": "光模組監控",
                "series_names": ["tx", "rx"],
                "data": [
                    {
                        "timestamp": "2024-01-15T10:00:00Z",
                        "values": {"tx": 95.5, "rx": 92.3}
                    },
                    {
                        "timestamp": "2024-01-15T10:05:00Z",
                        "values": {"tx": 96.0, "rx": 93.1}
                    }
                ]
            }
        }


class RawDataRowSchema(BaseModel):
    """原始資料表格的一行。"""
    values: dict[str, Any] = Field(
        ...,
        description="欄位名稱到值的映射"
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
    
    class Config:
        json_schema_extra = {
            "example": {
                "indicator_name": "transceiver",
                "title": "光模組原始資料",
                "columns": [
                    {"key": "switch_hostname", "title": "Switch"},
                    {"key": "interface_name", "title": "Interface"},
                    {"key": "tx_power", "title": "Tx (dBm)"},
                    {"key": "rx_power", "title": "Rx (dBm)"},
                    {"key": "tx_pass", "title": "Tx Pass"},
                    {"key": "rx_pass", "title": "Rx Pass"},
                    {"key": "collected_at", "title": "收集時間"},
                ],
                "rows": [
                    {
                        "switch_hostname": "switch-01",
                        "interface_name": "Ethernet1/1",
                        "tx_power": -2.5,
                        "rx_power": -5.8,
                        "tx_pass": True,
                        "rx_pass": True,
                        "collected_at": "2024-01-15T10:30:00Z"
                    }
                ],
                "total": 100,
                "page": 1,
                "page_size": 50
            }
        }


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
    
    class Config:
        json_schema_extra = {
            "example": {
                "indicators": [
                    {
                        "name": "transceiver",
                        "title": "光模組監控",
                        "current_pass_rates": {"tx": 95.5, "rx": 92.3},
                        "trend": "stable"
                    }
                ],
                "total_switches": 10,
                "active_switches": 9,
                "total_interfaces": 480
            }
        }


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
    status: str  # CollectionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_items: int = 0
    success_items: int = 0
    failed_items: int = 0
    error_message: Optional[str] = None
