# auth-service/app/main.py
import logging
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.endpoints.auth import router as auth_router
from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.api.v1.endpoints.internal import router as internal_router


# ─── Setup Logging ─────────────────────────────────────────
def configure_logging():
    """Configure logging with proper format."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger(__name__)


# ─── Database Initialization ──────────────────────────────
def wait_for_db(retries: int = 15, delay: float = 3.0) -> None:
    """Wait for MySQL to be ready before starting.
    
    Args:
        retries: Number of retry attempts
        delay: Delay in seconds between attempts
        
    Raises:
        RuntimeError: If database is not available after all retries
    """
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("[DB] ✓ MySQL is ready")
            return
        except Exception as e:
            logger.warning(
                "[DB] MySQL not ready (attempt %d/%d): %s",
                attempt,
                retries,
                str(e),
            )
            time.sleep(delay)

    raise RuntimeError(
        f"[DB] MySQL not available after {retries} attempts. Exiting."
    )


def bootstrap_super_admin() -> None:
    """Create initial SUPER_ADMIN user if none exists."""
    db = SessionLocal()
    try:
        # Check if superadmin already exists
        existing = (
            db.query(User)
            .filter(User.role == UserRole.SUPER_ADMIN.value)
            .first()
        )
        
        if existing:
            logger.info(
                "[AUTH] Superadmin already exists: %s (%s)",
                existing.username,
                existing.email,
            )
            return

        # Create new superadmin
        now = datetime.now(timezone.utc)
        user = User(
            username=settings.INITIAL_SUPERADMIN_USERNAME,
            email=settings.INITIAL_SUPERADMIN_EMAIL,
            full_name=settings.INITIAL_SUPERADMIN_FULL_NAME,
            password_hash=get_password_hash(settings.INITIAL_SUPERADMIN_PASSWORD),
            role=UserRole.SUPER_ADMIN.value,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(
            "[AUTH] ✓ Superadmin '%s' created successfully (ID: %d)",
            settings.INITIAL_SUPERADMIN_USERNAME,
            user.id,
        )
        
    except Exception as e:
        logger.error(
            "[AUTH] ✗ Failed to create superadmin: %s",
            str(e),
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()


# ─── App Lifespan ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("[APP] Starting %s v1.0.0", settings.APP_NAME)
    logger.info("[APP] Environment: %s", settings.ENVIRONMENT)
    logger.info("[APP] Log Level: %s", settings.LOG_LEVEL)
    logger.info("[APP] Database: %s@%s:%s/%s",
                settings.DB_USER,
                settings.DB_HOST,
                settings.DB_PORT,
                settings.DB_NAME)
    logger.info("=" * 60)

    # Wait for database and initialize
    wait_for_db()
    Base.metadata.create_all(bind=engine)
    bootstrap_super_admin()

    logger.info("[APP] ✓ Service ready")

    yield

    # Shutdown
    logger.info("[APP] Shutting down %s...", settings.APP_NAME)
    logger.info("[APP] ✓ Shutdown complete")


# ─── CORS Configuration ───────────────────────────────────
def get_cors_origins() -> list[str]:
    """Get CORS origins based on environment.
    
    Returns:
        List of allowed CORS origins
    """
    if settings.ENVIRONMENT == "production":
        # In production, specify explicit origins
        return [
            "https://yourdomain.com",
            "https://www.yourdomain.com",
        ]
    else:
        # In development, allow common local URLs
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://0.0.0.0:5173",
            "http://frontend:5173",  # Docker
            "*",  # Allow all in dev
        ]


# ─── App Factory ──────────────────────────────────────────
def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    configure_logging()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Authentication microservice (JWT + MySQL + Role-Based Access Control)",
        docs_url="/api/v1/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/api/v1/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/api/v1/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # ─── CORS Middleware ──────────────────────────────────
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
        max_age=600,  # Cache preflight for 10 minutes
    )

    # ─── Routes ──────────────────────────────────
    app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(internal_router, prefix="/internal", tags=["internal"])

    # ─── Health Check ────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Health check endpoint")
    async def health_check():
        """Check service and database health status."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as e:
            logger.warning("[HEALTH] Database check failed: %s", str(e))
            db_ok = False

        return {
            "status": "healthy" if db_ok else "degraded",
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "db_connected": db_ok,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "JWT Authentication",
                "Role-Based Access Control",
                "Token Refresh",
                "MySQL Integration",
            ],
        }

    logger.info("[APP] FastAPI application created successfully")
    return app


# ─── Application Instance ─────────────────────────────────
app = create_app()