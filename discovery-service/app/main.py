# discovery-service/app/main.py
import logging
import threading
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import init_db
from app.core.logging_config import setup_logging
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers import discovery, switches, rpis, hgws, topology, sync
from app.services.sync_service import run_sync_now, get_sync_status


# ─── Setup Logging ─────────────────────────────────────────
setup_logging(
    app_name=settings.APP_NAME,
    log_level=settings.LOG_LEVEL,
    enable_json=True,
)

logger = logging.getLogger(__name__)

_scheduler_stop = threading.Event()


# ─── Scheduler Loop ───────────────────────────────────────
def _scheduler_loop() -> None:
    """Background thread for scheduled sync operations."""
    logger.info(
        "[SCHEDULER] Started. Daily sync scheduled for %02d:%02d UTC",
        settings.SYNC_HOUR,
        settings.SYNC_MINUTE,
    )
    last_run_date = None

    while not _scheduler_stop.is_set():
        now = datetime.utcnow()
        today = now.date()

        if (
            settings.SYNC_ENABLED
            and now.hour == settings.SYNC_HOUR
            and now.minute == settings.SYNC_MINUTE
            and last_run_date != today
        ):
            logger.info(
                "[SCHEDULER] Triggering scheduled daily sync at %s",
                now.isoformat(),
            )
            last_run_date = today
            try:
                run_id = run_sync_now(triggered_by="scheduler")
                logger.info(
                    "[SCHEDULER] ✓ Scheduled sync completed (run_id=%d)",
                    run_id,
                )
            except Exception as e:
                logger.error(
                    "[SCHEDULER] ✗ Scheduled sync failed: %s",
                    str(e),
                    exc_info=True,
                )

        _scheduler_stop.wait(timeout=30)


# ─── App Lifespan ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app startup and shutdown events."""
    # Startup
    logger.info("=" * 70)
    logger.info("[APP] Starting %s v1.0.0", settings.APP_NAME)
    logger.info("[APP] Environment: %s", settings.ENVIRONMENT)
    logger.info("[APP] Log Level: %s", settings.LOG_LEVEL)
    logger.info("[APP] Database: %s@%s:%s/%s",
                settings.DB_USER,
                settings.DB_HOST,
                settings.DB_PORT,
                settings.DB_NAME)
    logger.info("[APP] Scheduler: %s (daily at %02d:%02d UTC)",
                "Enabled" if settings.SYNC_ENABLED else "Disabled",
                settings.SYNC_HOUR,
                settings.SYNC_MINUTE)
    logger.info("=" * 70)

    # Initialize database
    init_db()

    # Start scheduler thread
    scheduler = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="SyncSchedulerThread",
    )
    scheduler.start()
    logger.info("[APP] ✓ Scheduler thread started")
    logger.info("[APP] ✓ Service ready")

    yield

    # Shutdown
    logger.info("[APP] Shutting down %s...", settings.APP_NAME)
    _scheduler_stop.set()
    scheduler.join(timeout=5)
    logger.info("[APP] ✓ Shutdown complete")


# ─── CORS Configuration ───────────────────────────────────
def get_cors_origins() -> list[str]:
    """Get CORS origins based on environment."""
    if settings.ENVIRONMENT == "production":
        return [
            "https://yourdomain.com",
            "https://www.yourdomain.com",
        ]
    else:
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://0.0.0.0:5173",
            "http://frontend:5173",  # Docker
            "*",
        ]


# ─── App Factory ──────────────────────────────────────────
def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Discovery & Monitoring Service",
        version="1.0.0",
        description="Network topology discovery: Switches → RPis → HGWs",
        docs_url="/api/v1/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/api/v1/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/api/v1/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # ─── Middlewares ──────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)
    
    cors_origins = get_cors_origins()
    logger.info("[CORS] Allowed origins: %s", cors_origins)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-CSRF-Token",
        ],
        expose_headers=[
            "Content-Length",
            "X-Total-Count",
            "X-Page-Count",
        ],
        max_age=600,
    )

    # On ajoute le nom de la ressource après /api/v1
    app.include_router(discovery.router, tags=["Discovery"])
    app.include_router(switches.router,  tags=["Switches"])
    app.include_router(rpis.router, tags=["RPis"])
    app.include_router(hgws.router,  tags=["HGWs"])
    app.include_router(topology.router,  tags=["Topology"])
    app.include_router(sync.router,  tags=["Sync"])

    # ─── Health Check ────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Health check endpoint")
    async def health_check():
        """Check service and database health status."""
        from app.core.db import check_db_connection
        
        db_ok = check_db_connection()
        sync_status = get_sync_status()

        return {
            "status": "healthy" if db_ok else "degraded",
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "db_connected": db_ok,
            "sync": sync_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ─── Info Endpoint ───────────────────────────────────
    @app.get("/api/v1/info", tags=["Info"], summary="Service information")
    async def service_info():
        """Get service information."""
        return {
            "name": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "features": [
                "Network Discovery",
                "Topology Mapping",
                "Device Monitoring",
                "Scheduled Sync",
                "Multi-Protocol Support",
            ],
        }

    # ─── Logs Endpoints ──────────────────────────────────
    @app.get("/api/v1/logs/files", tags=["Logs"])
    async def list_log_files():
        """List available log files."""
        from pathlib import Path
        
        logs_dir = Path("/app/logs")
        if not logs_dir.exists():
            return {"files": [], "logs_dir": str(logs_dir)}

        files = []
        for f in sorted(logs_dir.glob("*.log")):
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return {"files": files, "logs_dir": str(logs_dir), "count": len(files)}

    @app.get("/api/v1/logs/tail", tags=["Logs"])
    async def tail_log(
        filename: str = "discovery-service.log",
        lines: int = 100,
    ):
        """Read last N lines of a log file."""
        from pathlib import Path
        import json

        log_file = Path("/app/logs") / filename

        if not log_file.exists():
            return {
                "filename": filename,
                "error": f"File not found",
                "available_logs": [
                    f.name for f in Path("/app/logs").glob("*.log")
                ] if Path("/app/logs").exists() else [],
            }

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()

            last_lines = all_lines[-lines:]
            parsed = []

            for line in last_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed.append(json.loads(line))
                except json.JSONDecodeError:
                    parsed.append({"message": line, "raw": True})

            return {
                "filename": filename,
                "total_lines": len(all_lines),
                "returned_lines": len(parsed),
                "lines": parsed,
            }
        except Exception as e:
            logger.error("[LOGS] Error reading file %s: %s", filename, str(e))
            return {
                "filename": filename,
                "error": str(e),
            }

    logger.info("[APP] FastAPI application created successfully")
    return app


# ─── Application Instance ─────────────────────────────────
app = create_app()