"""
Network Dashboard - FastAPI Application Entry Point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.base import close_db, init_db
from app.fetchers.registry import setup_fetchers
from app.parsers.registry import auto_discover_parsers
from app.services.scheduler import get_scheduler_service, setup_scheduled_jobs

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.app_debug else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_scheduler_config() -> dict[str, Any]:
    """
    Load scheduler configuration from YAML file.

    此設定檔是通用的，不包含特定的 maintenance_id。
    採集時會自動查詢所有活躍的歲修 ID。

    Returns:
        dict with 'jobs' list.
        Each job has: name, url, source, brand, interval, description.
    """
    config_path = Path("config/scheduler.yaml")
    if not config_path.exists():
        logger.warning("scheduler.yaml not found, no jobs will be scheduled")
        return {"jobs": []}

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "jobs" not in config:
        return {"jobs": []}

    jobs = []
    for job_name, job_config in config["jobs"].items():
        if not job_config:
            job_config = {}

        # 檢查 enabled 標誌（預設為 True）
        if not job_config.get("enabled", True):
            logger.info(f"Skipping disabled job: {job_name}")
            continue

        jobs.append({
            "name": job_name,
            "url": job_config.get("url"),
            "source": job_config.get("source"),
            "brand": job_config.get("brand"),
            "interval": job_config.get("interval", 30),
            "description": job_config.get("description", ""),
        })

    return {"jobs": jobs}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan management.

    Startup: Initialize database, discover parsers, start scheduler.
    Shutdown: Stop scheduler, close database connections.
    """
    # Startup
    logger.info("Starting application...")
    await init_db()
    auto_discover_parsers()
    setup_fetchers(use_mock=settings.use_mock_api)

    # Load and start scheduled jobs
    scheduler_config = load_scheduler_config()
    jobs = scheduler_config.get("jobs", [])
    if jobs:
        await setup_scheduled_jobs(jobs)
        logger.info(f"Started {len(jobs)} scheduled jobs")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    scheduler = get_scheduler_service()
    scheduler.stop()
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="網路設備歲修監控 Dashboard API",
        version="0.3.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler for database integrity errors
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        """
        Handle database integrity errors (e.g., unique constraint violations).

        Convert IntegrityError to user-friendly 400 Bad Request response.
        """
        error_msg = str(exc.orig) if exc.orig else str(exc)

        # Parse common constraint violation patterns
        if "Duplicate entry" in error_msg or "UNIQUE constraint" in error_msg:
            detail = "資料重複：該記錄已存在"
        elif "foreign key constraint" in error_msg.lower():
            detail = "關聯錯誤：引用的資料不存在"
        else:
            detail = f"資料庫約束錯誤：{error_msg}"

        logger.warning(f"IntegrityError on {request.url}: {error_msg}")

        return JSONResponse(
            status_code=400,
            content={"detail": detail},
        )

    # Import and include routers
    from app.api.routes import api_router

    app.include_router(api_router, prefix=settings.api_prefix)

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, Any]:
        """Health check endpoint."""
        scheduler = get_scheduler_service()
        return {
            "status": "ok",
            "version": "0.3.0",
            "scheduler_running": scheduler.is_running(),
            "scheduled_jobs": len(scheduler.get_jobs()),
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_debug,
    )
