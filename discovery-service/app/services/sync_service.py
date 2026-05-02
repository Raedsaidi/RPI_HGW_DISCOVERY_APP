import logging
import threading
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.config import settings
from app.services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)

# Global scheduler state
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False
_last_sync_run_id: Optional[int] = None
_last_sync_at: Optional[datetime] = None
_last_sync_status: Optional[str] = None


def run_sync_now(triggered_by: str = "scheduler") -> int:
    """Run discovery synchronously and return run_id."""
    global _last_sync_run_id, _last_sync_at, _last_sync_status

    db: Session = SessionLocal()
    try:
        service = DiscoveryService(db)
        run_id = service.run(triggered_by=triggered_by)
        _last_sync_run_id = run_id
        _last_sync_at = datetime.utcnow()
        _last_sync_status = "completed"
        return run_id
    except Exception as e:
        logger.error("[SYNC] Sync failed: %s", e)
        _last_sync_status = f"error: {e}"
        raise
    finally:
        db.close()


def get_sync_status() -> dict:
    return {
        "enabled": settings.SYNC_ENABLED,
        "hour": settings.SYNC_HOUR,
        "minute": settings.SYNC_MINUTE,
        "timezone": settings.SYNC_TIMEZONE,
        "last_run_id": _last_sync_run_id,
        "last_sync_at": _last_sync_at.isoformat() if _last_sync_at else None,
        "last_sync_status": _last_sync_status,
    }