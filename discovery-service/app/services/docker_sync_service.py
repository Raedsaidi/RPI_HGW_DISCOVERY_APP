# app/services/docker_sync_service.py
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.services.docker_clients_sync_service import DockerClientsSyncService

logger = logging.getLogger(__name__)

_last_docker_sync_run_id: Optional[int] = None
_last_docker_sync_at: Optional[datetime] = None
_last_docker_sync_status: Optional[str] = None


def run_docker_sync_now(triggered_by: str = "docker_scheduler") -> tuple[bool, Optional[int], str]:
    """
    Run docker sync for latest finished run.
    """
    global _last_docker_sync_run_id, _last_docker_sync_at, _last_docker_sync_status

    db: Session = SessionLocal()
    try:
        svc = DockerClientsSyncService(db)
        ok, run_id, msg = svc.sync_latest_finished_run()

        _last_docker_sync_run_id = run_id
        _last_docker_sync_at = datetime.utcnow()
        _last_docker_sync_status = ("ok: " if ok else "skip/fail: ") + msg

        if ok:
            logger.info("[DOCKER_SYNC] %s (run_id=%s)", msg, run_id)
        else:
            logger.info("[DOCKER_SYNC] %s (run_id=%s)", msg, run_id)

        return ok, run_id, msg
    except Exception as e:
        _last_docker_sync_status = f"error: {e}"
        logger.error("[DOCKER_SYNC] failed: %s", e, exc_info=True)
        return False, None, str(e)
    finally:
        db.close()


def get_docker_sync_status() -> dict:
    return {
        "last_run_id": _last_docker_sync_run_id,
        "last_sync_at": _last_docker_sync_at.isoformat() if _last_docker_sync_at else None,
        "last_status": _last_docker_sync_status,
    }