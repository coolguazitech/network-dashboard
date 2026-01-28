"""
API router configuration.

Aggregates all endpoint routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import (
    categories,
    comparisons,
    dashboard,
    expectations,
    indicators,
    mac_list,
    maintenance,
    maintenance_devices,
    switches,
)

api_router = APIRouter()

# Include routers
api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"],
)

api_router.include_router(
    switches.router,
    prefix="/switches",
    tags=["Switches"],
)

api_router.include_router(
    comparisons.router,
    prefix="",
    tags=["Comparison"],
)

api_router.include_router(
    maintenance.router,
    prefix="",
    tags=["Maintenance"],
)

api_router.include_router(
    categories.router,
    prefix="",
    tags=["Categories"],
)

api_router.include_router(
    mac_list.router,
    prefix="",
    tags=["MAC List"],
)

api_router.include_router(
    maintenance_devices.router,
    prefix="",
    tags=["Maintenance Devices"],
)

api_router.include_router(
    expectations.router,
    prefix="/expectations",
    tags=["Expectations"],
)

api_router.include_router(
    indicators.router,
    prefix="/indicators",
    tags=["Indicators"],
)
