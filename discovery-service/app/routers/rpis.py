from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
import asyncio
import json

from app.services.terminal_manager import terminal_manager, decode_jwt_user
from app.core.db import get_db
from app.core.security import require_read_access, require_write_access
from app.repositories.rpi_repo import RpiRepository
from app.schemas.rpi import RpiCredentialSubmit
from app.services.rpi_reboot_service import RpiRebootService
from app.models.rpi import Rpi, RpiFact
from app.services.reconnect_service import ReconnectService

router = APIRouter(prefix="/api/v1/rpis", tags=["RPis"])


@router.get("")
def list_rpis(
    search: Optional[str] = Query(None, description="Search by IP, MAC, hostname or label"),
    switch_ip: Optional[str] = Query(None, description="Filter by switch IP"),
    hgw_ip: Optional[str] = Query(None, description="Filter by HGW IP (gateway address from ip r s)"),
    ssh_success: Optional[bool] = Query(None, description="Filter by SSH success status"),
    has_custom_creds: Optional[bool] = Query(None, description="Filter RPis with custom credentials"),
    label: Optional[str] = Query(None, description="Filter by label/group"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    q = db.query(Rpi)

    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(Rpi.ip_mgmt.ilike(pattern), Rpi.mac.ilike(pattern), Rpi.label.ilike(pattern)))

    if switch_ip:
        q = q.filter(Rpi.switch_ip == switch_ip)

    if hgw_ip:
        q = q.filter(Rpi.hgw_ip == hgw_ip)

    if ssh_success is not None:
        q = q.filter(Rpi.last_ssh_success == ssh_success)

    if has_custom_creds is not None:
        if has_custom_creds:
            q = q.filter(Rpi.custom_ssh_user.isnot(None))
        else:
            q = q.filter(Rpi.custom_ssh_user.is_(None))

    if label:
        q = q.filter(Rpi.label.ilike(f"%{label}%"))

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    order_expr = func.coalesce(func.inet_aton(func.trim(Rpi.ip_mgmt)), 4294967295)

    rpis = (
        q.order_by(order_expr.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = []
    for rpi in rpis:
        result.append(
            {
                "id": rpi.id,
                "mac": rpi.mac,
                "ip_mgmt": rpi.ip_mgmt,
                "label": rpi.label,
                "switch_ip": rpi.switch_ip,
                "switch_port": rpi.switch_port,
                "hgw_ip": rpi.hgw_ip,
                "last_seen": rpi.last_seen,
                "last_ssh_success": rpi.last_ssh_success,
                "last_ssh_error": rpi.last_ssh_error,
                "has_custom_credentials": bool(rpi.custom_ssh_user),
            }
        )

    return {"data": result, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.get("/terminal/sessions")
def list_all_rpi_terminal_sessions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    return {"data": terminal_manager.list_user_sessions(username, device_type="rpi")}


@router.get("/{ip_mgmt}")
def get_rpi(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    rpi = RpiRepository(db).get_by_ip(ip_mgmt)
    if not rpi:
        raise HTTPException(status_code=404, detail="RPi not found.")
    return rpi


@router.get("/{ip_mgmt}/facts")
def get_rpi_facts(
    ip_mgmt: str,
    run_id: Optional[int] = Query(None, description="Filter by specific run"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    q = db.query(RpiFact).filter(RpiFact.rpi_ip_mgmt == ip_mgmt)

    if run_id:
        q = q.filter(RpiFact.run_id == run_id)

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    facts = (
        q.order_by(RpiFact.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {"data": facts, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("/credentials", status_code=200)
def submit_rpi_credentials(
    body: RpiCredentialSubmit,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = RpiRepository(db)
    rpi = repo.get_by_ip(body.rpi_ip_mgmt)
    if not rpi:
        raise HTTPException(status_code=404, detail="RPi not found.")

    repo.save_credential_override(
        ip_mgmt=body.rpi_ip_mgmt,
        ssh_user=body.ssh_user,
        ssh_pass=body.ssh_pass,
        submitted_by=current_user["username"],
    )
    return {
        "message": f"Credentials saved for RPi {body.rpi_ip_mgmt}. Will be tried first in the next discovery run.",
        "rpi_ip": body.rpi_ip_mgmt,
    }


@router.delete("/{ip_mgmt}/credentials")
def delete_rpi_credentials(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = RpiRepository(db)
    rpi = repo.get_by_ip(ip_mgmt)
    if not rpi:
        raise HTTPException(status_code=404, detail="RPi not found.")

    rpi.custom_ssh_user = None
    rpi.custom_ssh_pass = None
    db.commit()

    return {"message": f"Custom credentials removed for RPi {ip_mgmt}. Will try pi/raspberry then root/sah."}


@router.post("/{ip_mgmt}/reconnect")
def reconnect_rpi(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    try:
        return ReconnectService(db).reconnect_rpi(ip_mgmt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RPi reconnect failed: {e}")


# ─────────────────────────────────────────────────────────────
# TERMINAL
# ─────────────────────────────────────────────────────────────
@router.post("/{ip_mgmt}/terminal/open")
def open_rpi_terminal(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    try:
        sess = terminal_manager.open_rpi(db, owner=username, rpi_ip=ip_mgmt)
        return {"session_id": sess.id, "device_type": "rpi", "ip": ip_mgmt, "status": sess.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{ip_mgmt}/terminal/sessions")
def list_rpi_terminal_sessions(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    return {"data": terminal_manager.list_user_sessions(username, device_type="rpi", target=ip_mgmt)}


@router.post("/terminal/{session_id}/close")
def close_rpi_terminal_session(
    session_id: str,
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    sess = terminal_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.owner != username:
        raise HTTPException(status_code=403, detail="Not allowed")
    terminal_manager.force_close(session_id)
    return {"message": "Session closed"}


@router.websocket("/terminal/{session_id}/ws")
async def rpi_terminal_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "auth" or not msg.get("token"):
            await websocket.close(code=1008)
            return
        user = decode_jwt_user(msg["token"])
        username = user["username"]
    except Exception:
        await websocket.close(code=1008)
        return

    sess = terminal_manager.get(session_id)
    if not sess:
        await websocket.send_text(json.dumps({"type": "status", "status": "error", "error": "Session not found"}))
        await websocket.close(code=1008)
        return
    if sess.owner != username or sess.device_type != "rpi":
        await websocket.close(code=1008)
        return

    try:
        sess.add_client(websocket)
        sess.start_reader(asyncio.get_running_loop())
        await sess.send_buffer(websocket)
        await websocket.send_text(json.dumps({"type": "status", "status": sess.status, "error": sess.error}, ensure_ascii=False))

        while True:
            try:
                raw_in = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                if sess.status in ("closed", "error"):
                    await websocket.close(code=1000)
                    return
                continue

            try:
                m = json.loads(raw_in)
            except Exception:
                continue

            t = m.get("type")
            if t == "input":
                sess.send_input(m.get("data", ""))
            elif t == "resize":
                sess.resize(int(m.get("cols", 220)), int(m.get("rows", 60)))
            elif t == "ping":
                sess.touch_seen()
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif t == "close":
                terminal_manager.force_close(session_id)
                await websocket.close(code=1000)
                return

    except WebSocketDisconnect:
        pass
    finally:
        try:
            sess.remove_client(websocket)
        except Exception:
            pass


@router.post("/{ip_mgmt}/reboot")
def reboot_rpi(
    ip_mgmt: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    try:
        return RpiRebootService(db).reboot_rpi(ip_mgmt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RPi reboot failed: {e}")