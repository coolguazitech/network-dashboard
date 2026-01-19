"""
API router configuration.

Aggregates all endpoint routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.endpoints import dashboard, switches, comparisons

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
