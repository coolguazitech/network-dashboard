"""
Network Dashboard - FastAPI Application Entry Point.
"""
from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

import re

from app.core.config import settings
from app.db.base import close_db, init_db

# 從 URL 路徑中提取 maintenance_id（用於日誌關聯）
_MAINTENANCE_ID_RE = re.compile(r"/maintenance/([^/]+)")


def _extract_maintenance_id(path: str) -> str | None:
    """嘗試從 API 路徑中提取 maintenance_id。"""
    m = _MAINTENANCE_ID_RE.search(path)
    return m.group(1) if m else None
from app.fetchers.registry import setup_fetchers
from app.parsers.registry import auto_discover_parsers
from app.services.scheduler import get_scheduler_service, setup_scheduled_jobs

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.app_debug else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_fetcher_config() -> dict[str, Any]:
    """
    Load fetcher and task configuration from YAML file.

    讀取 config/scheduler.yaml，回傳兩部分：
    - fetchers: {name: {source, endpoint, interval}} — 用於 ConfiguredFetcher
    - jobs: [{name, interval}] — 所有排程任務（fetchers + tasks 合併）

    Returns:
        dict with 'fetchers' and 'jobs' keys.
    """
    config_path = Path("config/scheduler.yaml")
    if not config_path.exists():
        logger.warning("scheduler.yaml not found, no jobs will be scheduled")
        return {"fetchers": {}, "jobs": []}

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config:
        return {"fetchers": {}, "jobs": []}

    default_interval = settings.collection_interval_seconds
    fetchers: dict[str, dict[str, Any]] = {}
    jobs: list[dict[str, Any]] = []

    # Parse fetchers section
    for name, fc in (config.get("fetchers") or {}).items():
        if not fc:
            fc = {}
        if not fc.get("enabled", True):
            logger.info(f"Skipping disabled fetcher: {name}")
            continue

        fetchers[name] = {
            "source": fc.get("source", ""),
        }
        jobs.append({
            "name": name,
            "interval": fc.get("interval", default_interval),
            "source": fc.get("source", ""),
        })

    # Parse tasks section
    for name, tc in (config.get("tasks") or {}).items():
        if not tc:
            tc = {}
        if not tc.get("enabled", True):
            logger.info(f"Skipping disabled task: {name}")
            continue

        jobs.append({
            "name": name,
            "interval": tc.get("interval", default_interval),
        })

    return {"fetchers": fetchers, "jobs": jobs}


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

    # Ensure MinIO bucket exists
    from app.services.storage import ensure_bucket
    try:
        await ensure_bucket()
    except Exception as e:
        logger.warning("MinIO bucket init failed (uploads may not work): %s", e)

    auto_discover_parsers()

    # Load fetcher config from YAML
    fetcher_config = load_fetcher_config()
    setup_fetchers(
        fetcher_configs=fetcher_config.get("fetchers"),
    )

    # Threshold overrides: per-maintenance, loaded lazily on first access

    # Start scheduled jobs
    jobs = fetcher_config.get("jobs", [])
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

        # 寫入 SystemLog
        from app.services.system_log import write_log, format_error_detail
        await write_log(
            level="WARNING",
            source="api",
            summary=f"資料庫約束錯誤 ({type(exc).__name__}): {request.method} {request.url.path}",
            detail=format_error_detail(
                exc=exc,
                context={
                    "請求": f"{request.method} {request.url.path}",
                    "約束": error_msg,
                    "客戶端": request.client.host if request.client else "unknown",
                },
            ),
            module="database",
            maintenance_id=_extract_maintenance_id(str(request.url.path)),
            request_path=str(request.url.path),
            request_method=request.method,
            status_code=400,
            ip_address=request.client.host if request.client else None,
        )

        return JSONResponse(
            status_code=400,
            content={"detail": detail},
        )

    # Global exception handler for uncaught exceptions
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        攔截所有未處理的 500 錯誤，寫入 SystemLog。
        """
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method, request.url.path, exc,
        )

        from app.services.system_log import write_log, format_error_detail
        await write_log(
            level="ERROR",
            source="api",
            summary=f"API 錯誤 ({type(exc).__name__}): {request.method} {request.url.path}",
            detail=format_error_detail(
                exc=exc,
                context={
                    "請求": f"{request.method} {request.url.path}",
                    "客戶端": request.client.host if request.client else "unknown",
                },
            ),
            module="api",
            maintenance_id=_extract_maintenance_id(str(request.url.path)),
            request_path=str(request.url.path),
            request_method=request.method,
            status_code=500,
            ip_address=request.client.host if request.client else None,
        )

        return JSONResponse(
            status_code=500,
            content={"detail": "內部伺服器錯誤"},
        )

    # API endpoints
    from app.api.endpoints import (
        auth,
        cases,
        categories,
        comparisons,
        contacts,
        dashboard,
        expectations,
        indicators,
        mac_list,
        maintenance,
        maintenance_devices,
        meals,
        reports,
        system_logs,
        thresholds,
        uploads,
        users,
    )

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix, tags=["Auth"])
    app.include_router(maintenance.router, prefix=prefix, tags=["Maintenance"])
    app.include_router(maintenance_devices.router, prefix=prefix, tags=["Maintenance Devices"])
    app.include_router(dashboard.router, prefix=f"{prefix}/dashboard", tags=["Dashboard"])
    app.include_router(indicators.router, prefix=f"{prefix}/indicators", tags=["Indicators"])
    app.include_router(thresholds.router, prefix=prefix, tags=["Thresholds"])
    app.include_router(expectations.router, prefix=f"{prefix}/expectations", tags=["Expectations"])
    app.include_router(contacts.router, prefix=prefix, tags=["Contacts"])
    app.include_router(categories.router, prefix=prefix, tags=["Categories"])
    app.include_router(comparisons.router, prefix=prefix, tags=["Comparisons"])
    app.include_router(cases.router, prefix=prefix, tags=["Cases"])
    app.include_router(mac_list.router, prefix=prefix, tags=["MAC List"])
    app.include_router(meals.router, prefix=prefix, tags=["Meals"])
    app.include_router(reports.router, prefix=prefix, tags=["Reports"])
    app.include_router(system_logs.router, prefix=prefix, tags=["System Logs"])
    app.include_router(users.router, prefix=prefix, tags=["Users"])
    app.include_router(uploads.router, prefix=prefix, tags=["Uploads"])

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

    # Mount static files (for production - built frontend)
    # 靜態檔案路徑：Docker 內為 /app/static，本地開發為 frontend/dist
    static_paths = [
        Path("/app/static"),           # Docker 容器內
        Path("static"),                # 本地 static 目錄
        Path("frontend/dist"),         # 本地開發 build 後
    ]

    static_dir = None
    for path in static_paths:
        if path.exists() and path.is_dir():
            static_dir = path
            break

    if static_dir:
        # Serve static assets (js, css, images) - only if assets dir exists
        assets_dir = static_dir / "assets"
        if assets_dir.exists() and assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=assets_dir),
                name="assets",
            )

        # Serve index.html for root and SPA routes
        @app.get("/")
        async def serve_root() -> FileResponse:
            """Serve frontend index.html."""
            return FileResponse(static_dir / "index.html")

        # Catch-all for SPA routing (must be after API routes)
        @app.get("/{path:path}")
        async def serve_spa(path: str) -> FileResponse:
            """Serve index.html for SPA client-side routing."""
            # 如果是 API 或已知路徑，返回 404
            if path.startswith("api/") or path == "health":
                raise HTTPException(status_code=404, detail="Not found")

            # 檢查是否為靜態檔案
            file_path = static_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)

            # 否則返回 index.html (SPA routing)
            return FileResponse(static_dir / "index.html")

        logger.info(f"Static files mounted from: {static_dir}")
    else:
        logger.warning(
            "No static directory found. Frontend will not be served. "
            "Run 'npm run build' in frontend/ or use Docker image."
        )

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
