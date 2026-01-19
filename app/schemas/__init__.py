"""Pydantic schemas for API request/response models."""
from .switch import (
    SwitchCreate,
    SwitchUpdate,
    SwitchResponse,
    SwitchListResponse,
    InterfaceResponse,
)
from .indicator import (
    IndicatorMetadataResponse,
    TimeSeriesResponse,
    RawDataTableResponse,
    DashboardResponse,
)

__all__ = [
    "SwitchCreate",
    "SwitchUpdate",
    "SwitchResponse",
    "SwitchListResponse",
    "InterfaceResponse",
    "IndicatorMetadataResponse",
    "TimeSeriesResponse",
    "RawDataTableResponse",
    "DashboardResponse",
]
