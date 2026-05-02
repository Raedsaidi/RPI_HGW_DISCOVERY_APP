from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_read_access
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/api/v1/topology", tags=["Topology"])


@router.get("")
def get_latest_topology(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """Get topology for the latest discovery run."""
    service = TopologyService(db)
    run_id = service.get_latest_run_id()
    if not run_id:
        raise HTTPException(status_code=404, detail="No discovery run found.")
    return service.get_topology_for_run(run_id)


@router.get("/{run_id}")
def get_topology_for_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """Get topology for a specific discovery run."""
    service = TopologyService(db)
    run = service.discovery_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return service.get_topology_for_run(run_id)