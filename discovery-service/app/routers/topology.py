# app/api/topology_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_read_access
from app.schemas.user_schema import UserRole
from app.clients.user_client import UserServiceClient, get_user_client
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/api/v1/topology", tags=["Topology"])

FULL_ACCESS_ROLES = {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}


# ── Factory ──────────────────────────────────────────────────────────────────

def get_topology_service(
    db: Session = Depends(get_db),
    user_client: UserServiceClient = Depends(get_user_client),
) -> TopologyService:
    """Crée le TopologyService avec ses deux dépendances injectées."""
    return TopologyService(db=db, user_client=user_client)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
def get_latest_topology(
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    run_id = service.get_latest_run_id()
    if not run_id:
        raise HTTPException(status_code=404, detail="No discovery run found.")

    if current_user["role"] in FULL_ACCESS_ROLES:
        return service.get_topology_for_run(run_id)
    return service.get_topology_for_user(run_id, current_user["username"])


@router.get("/{run_id}")
def get_topology_for_run(
    run_id: int,
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    run = service.discovery_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    if current_user["role"] in FULL_ACCESS_ROLES:
        return service.get_topology_for_run(run_id)
    return service.get_topology_for_user(run_id, current_user["username"])


@router.get("/{run_id}/switch/{switch_ip}")
def get_topology_for_switch(
    run_id: int,
    switch_ip: str,
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    if current_user["role"] not in FULL_ACCESS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Switch-level filtering requires ADMIN or SUPER_ADMIN role.",
        )
    run = service.discovery_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return service.get_topology_for_switch(run_id, switch_ip)


@router.get("/{run_id}/hgw/{hgw_identifier}")
def get_topology_for_hgw(
    run_id: int,
    hgw_identifier: str,
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    run = service.discovery_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    # Access control: on garde la logique actuelle (identifiers = serial ou IP)
    if current_user["role"] not in FULL_ACCESS_ROLES:
        allowed = service.get_user_hgw_identifiers(current_user["username"])
        if hgw_identifier not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Access denied: this HGW is not assigned to your account.",
            )

    return service.get_topology_for_hgw(run_id, hgw_identifier)


@router.get("/{run_id}/my-hgws")
def get_my_hgws(
    run_id: int,
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    run = service.discovery_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    # ADMIN/SUPER_ADMIN: retourne une liste unique d'HGW
    if current_user["role"] in FULL_ACCESS_ROLES:
        full = service.get_topology_for_run(run_id)

        seen: dict[str, dict] = {}
        for sw in full.get("switches", []):
            for rpi in sw.get("rpis", []):
                hgw = rpi.get("hgw")
                if not hgw:
                    continue

                serial = hgw.get("serial_number")
                inst   = hgw.get("instance_key")
                ip     = hgw.get("ip")

                # NEW: ne plus dédupliquer par IP seule
                dedup_key = serial or inst or ip
                if not dedup_key or dedup_key in seen:
                    continue

                seen[dedup_key] = {
                    # ⚠️ compat: endpoint /hgw/{hgw_identifier} attend serial ou ip
                    "hgw_identifier": serial or ip,

                    "ip":            ip,
                    "serial_number": serial,
                    "instance_key":  inst,   # NEW: permet de distinguer les HGW qui partagent la même IP

                    "model_name":    hgw.get("model_name"),
                    "manufacturer":  hgw.get("manufacturer"),
                    "external_ip":   hgw.get("external_ip"),
                    "ssh_success":   hgw.get("ssh_success"),
                    "network":       hgw.get("network"),
                }

        return list(seen.values())

    # USER: laisse TopologyService filtrer par assignments
    return service.get_my_hgws(run_id, current_user["username"])