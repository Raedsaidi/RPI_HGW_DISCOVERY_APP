import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(retries: int = 15, delay: float = 3.0) -> bool:
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("[DB] MySQL is ready.")
            return True
        except Exception as e:
            logger.warning(
                "[DB] MySQL not ready (attempt %d/%d): %s",
                attempt, retries, e,
            )
            time.sleep(delay)
    return False


def init_db() -> None:
    # IMPORTANT: import models modules so SQLAlchemy registers tables
    from app.models import discovery_run, switch, rpi, hgw, rpi_docker  # noqa: F401

    if not wait_for_db(retries=15, delay=3.0):
        raise RuntimeError("Cannot connect to MySQL after retries.")

    Base.metadata.create_all(bind=engine)
    _apply_discovery_schema_patches()
    logger.info("[DB] Tables created/verified.")


def _apply_discovery_schema_patches() -> None:
    """Lightweight ALTERs for existing deployments (create_all does not add new columns)."""
    from sqlalchemy import text

    statements = [
        "ALTER TABLE hgws ADD COLUMN via_docker_container_id VARCHAR(128) NULL",
    ]
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.execute(text(sql))
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "1060" in msg:
                    continue
                logger.warning("[DB] schema patch skipped or failed: %s — %s", sql, e)


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("[DB] Connection check failed: %s", e)
        return False