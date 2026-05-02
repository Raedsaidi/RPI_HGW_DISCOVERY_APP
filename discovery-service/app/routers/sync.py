from fastapi import APIRouter, Depends, BackgroundTasks
from app.core.security import require_write_access, require_read_access
from app.services.sync_service import run_sync_now, get_sync_status
from app.core.config import settings

router = APIRouter(prefix="/api/v1/sync", tags=["Sync & Scheduler"])


@router.get("/status")
def sync_status(current_user: dict = Depends(require_read_access)):
    """Get scheduler and last sync status."""
    return get_sync_status()


@router.post("/trigger")
def trigger_sync(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_write_access),
):
    """Manually trigger the scheduled sync."""
    background_tasks.add_task(run_sync_now, f"manual:{current_user['username']}")
    return {
        "message": "Sync triggered in background.",
        "triggered_by": current_user["username"],
    }