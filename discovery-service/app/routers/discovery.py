# discovery-service/app/routers/discovery.py
import threading
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.core.db import get_db, SessionLocal
from app.core.security import require_write_access, require_read_access
from app.services.discovery_service import DiscoveryService
from app.repositories.discovery_repo import DiscoveryRepository
from app.schemas.discovery import DiscoveryRunRead, TriggerResponse
from app.models.discovery_run import DiscoveryRun, DeviceError

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])
logger = logging.getLogger(__name__)

_running_runs: set[int] = set()
_lock = threading.Lock()


def _run_in_background(run_id: int, triggered_by: str) -> None:
    """
    Exécute la discovery en background sur le *même* run_id déjà créé par l'API.
    Important: DiscoveryService.run() doit accepter run_id=...
    """
    db = SessionLocal()
    try:
        service = DiscoveryService(db)
        service.run(triggered_by=triggered_by, run_id=run_id)
    except Exception as e:
        logger.error("[ROUTER] Background discovery failed for run_id=%s: %s", run_id, e)

        # sécurité: si une exception sort du service, on marque le run en error
        try:
            DiscoveryRepository(db).finish_run(
                run_id=run_id,
                status="error",
                message=f"Background discovery crashed: {e}",
            )
        except Exception:
            logger.exception("[ROUTER] Failed to mark run as error (run_id=%s)", run_id)
    finally:
        db.close()
        with _lock:
            _running_runs.discard(run_id)


@router.post("/run", response_model=TriggerResponse)
def trigger_discovery(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    """Trigger a manual discovery run."""
    repo = DiscoveryRepository(db)
    run = repo.create_run(triggered_by=current_user["username"])
    run_id = run.id

    with _lock:
        _running_runs.add(run_id)

    background_tasks.add_task(_run_in_background, run_id, current_user["username"])

    return TriggerResponse(
        run_id=run_id,
        status="started",
        message=f"Discovery run #{run_id} started in background.",
    )


@router.get("/runs")
def list_runs(
    # Filtres
    status: Optional[str] = Query(None, description="Filter: running|done|error|partial"),
    triggered_by: Optional[str] = Query(None, description="Filter by who triggered"),
    # Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """List discovery runs with filters."""
    q = db.query(DiscoveryRun)

    if status:
        q = q.filter(DiscoveryRun.status == status)

    if triggered_by:
        q = q.filter(DiscoveryRun.triggered_by.ilike(f"%{triggered_by}%"))

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    runs = (
        q.order_by(DiscoveryRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "data": runs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/runs/{run_id}", response_model=DiscoveryRunRead)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    run = DiscoveryRepository(db).get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.delete("/runs/{run_id}")
def delete_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    if not DiscoveryRepository(db).delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"message": f"Run #{run_id} deleted."}


@router.get("/runs/{run_id}/errors")
def get_run_errors(
    run_id: int,
    # Filtres
    device_type: Optional[str] = Query(None, description="Filter: piserver|switch|rpi|hgw"),
    device_ip: Optional[str] = Query(None, description="Filter by device IP"),
    stage: Optional[str] = Query(None, description="Filter by stage: ssh|telnet|collect"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """Get errors for a run with optional filters."""
    q = db.query(DeviceError).filter(DeviceError.run_id == run_id)

    if device_type:
        q = q.filter(DeviceError.device_type == device_type)

    if device_ip:
        q = q.filter(DeviceError.device_ip.ilike(f"%{device_ip}%"))

    if stage:
        q = q.filter(DeviceError.stage == stage)

    return q.order_by(DeviceError.id).all()


@router.get("/status")
def discovery_status():
    with _lock:
        running = list(_running_runs)
    return {"running_run_ids": running, "is_running": len(running) > 0}