from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_read_access
from app.schemas.user_schema import UserRole
from app.clients.user_client import UserServiceClient, get_user_client
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/api/v1/topology", tags=["Topology"])

FULL_ACCESS_ROLES = {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}


def get_topology_service(
    db: Session = Depends(get_db),
    user_client: UserServiceClient = Depends(get_user_client),
) -> TopologyService:
    return TopologyService(db=db, user_client=user_client)


@router.get("")
def get_latest_topology(
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    run_id = service.get_latest_run_id()
    if not run_id:
        raise HTTPException(status_code=404, detail="No discovery run found.")

    has_full_access = (
        current_user["role"] in FULL_ACCESS_ROLES
        or service.user_has_all_hgws(current_user["username"])
    )

    if has_full_access:
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

    has_full_access = (
        current_user["role"] in FULL_ACCESS_ROLES
        or service.user_has_all_hgws(current_user["username"])
    )

    if has_full_access:
        return service.get_topology_for_run(run_id)
    return service.get_topology_for_user(run_id, current_user["username"])


@router.get("/{run_id}/switch/{switch_ip}")
def get_topology_for_switch(
    run_id: int,
    switch_ip: str,
    service: TopologyService = Depends(get_topology_service),
    current_user: dict = Depends(require_read_access),
):
    has_full_access = (
        current_user["role"] in FULL_ACCESS_ROLES
        or service.user_has_all_hgws(current_user["username"])
    )

    if not has_full_access:
        raise HTTPException(
            status_code=403,
            detail="Switch-level filtering requires ADMIN/SUPER_ADMIN or ALL assignment.",
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

    has_full_access = (
        current_user["role"] in FULL_ACCESS_ROLES
        or service.user_has_all_hgws(current_user["username"])
    )

    if not has_full_access:
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

    # ✅ ADMIN/SUPER_ADMIN: retourne une liste unique de TOUTES les HGWs
    if current_user["role"] in FULL_ACCESS_ROLES:
        full = service.get_topology_for_run(run_id)

        seen: dict[str, dict] = {}
        for sw in full.get("switches", []):
            for rpi in sw.get("rpis", []):
                hgw = rpi.get("hgw")
                if not hgw:
                    continue

                serial = hgw.get("serial_number")
                inst = hgw.get("instance_key")
                ip = hgw.get("ip")

                dedup_key = serial or inst or ip
                if not dedup_key or dedup_key in seen:
                    continue

                seen[dedup_key] = {
                    "hgw_identifier": serial or ip,
                    "ip": ip,
                    "serial_number": serial,
                    "instance_key": inst,
                    "model_name": hgw.get("model_name"),
                    "manufacturer": hgw.get("manufacturer"),
                    "external_ip": hgw.get("external_ip"),
                    "ssh_success": hgw.get("ssh_success"),
                    "network": hgw.get("network"),
                }

        return list(seen.values())

    # ✅ USER/PROJECT_MANAGER:
    # - if ALL only => service returns ALL HGWs
    # - if ALL + list => service returns only assigned HGWs (list)
    # - if list only => service returns assigned list
    return service.get_my_hgws(run_id, current_user["username"])