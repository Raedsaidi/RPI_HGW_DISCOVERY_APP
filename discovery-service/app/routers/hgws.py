from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
import asyncio, json
from app.services.terminal_manager import terminal_manager, decode_jwt_user

from app.core.db import get_db
from app.core.security import require_read_access, require_write_access
from app.repositories.hgw_repo import HgwRepository
from app.models.hgw import Hgw, HgwFact
from app.schemas.hgw import HgwRead, HgwListResponse

router = APIRouter(prefix="/api/v1/hgws", tags=["HGWs"])


@router.get("", response_model=HgwListResponse)
def list_hgws(
    # Recherche
    search: Optional[str] = Query(
        None, description="Search by IP, model, serial, external IP"
    ),
    # ── MODIFICATION : filtre par réseau (préfixe /24) au lieu de hgw_type ──
    network: Optional[str] = Query(
        None,
        description="Filter by network prefix (e.g., 192.168.1.x)",
        example="192.168.1.x",
    ),
    manufacturer: Optional[str] = Query(
        None, description="Filter by manufacturer"
    ),
    # Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """
    List all HGWs with filters.

    MODIFICATION : le filtre 'hgw_type' a été remplacé par 'network'
    qui filtre par préfixe réseau basé sur l'IP réelle de la gateway.
    """
    q = db.query(Hgw)

    # Search
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Hgw.ip.ilike(pattern),
                Hgw.model_name.ilike(pattern),
                Hgw.serial_number.ilike(pattern),
                Hgw.external_ip.ilike(pattern),
                Hgw.software_version.ilike(pattern),
                Hgw.manufacturer.ilike(pattern),
            )
        )

    # ── Filtre par réseau (préfixe /24) ───────────────────────────────────
    # network = "192.168.1.x" → on filtre les IPs qui commencent par "192.168.1."
    if network:
        # Convertir "192.168.1.x" en "192.168.1.%"
        prefix = network.replace(".x", ".").replace("x", "")
        if not prefix.endswith("."):
            prefix += "."
        q = q.filter(Hgw.ip.like(f"{prefix}%"))

    if manufacturer:
        q = q.filter(Hgw.manufacturer.ilike(f"%{manufacturer}%"))

    # Total
    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    hgws = (
        q.order_by(Hgw.ip.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "data": hgws,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/{ip}", response_model=HgwRead)
def get_hgw(
    ip: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """Get details for a specific HGW (by IP or serial)."""
    hgw = HgwRepository(db).get_by_identifier(ip)
    if not hgw:
        raise HTTPException(status_code=404, detail="HGW not found.")
    return hgw


@router.get("/{ip}/history")
def get_hgw_history(
    ip: str,
    run_id: Optional[int] = Query(None, description="Filter by specific run"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    """Get historical DeviceInfo facts for a HGW (by IP or serial)."""
    hgw = HgwRepository(db).get_by_identifier(ip)
    if hgw and hgw.serial_number:
        q = db.query(HgwFact).filter(HgwFact.serial_number == hgw.serial_number)
    else:
        q = db.query(HgwFact).filter(HgwFact.hgw_ip == ip)

    if run_id:
        q = q.filter(HgwFact.run_id == run_id)

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    facts = (
        q.order_by(HgwFact.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Sérialiser les facts avec last_seen depuis collected_at
    result = []
    for f in facts:
        result.append({
            "id": f.id,
            "run_id": f.run_id,
            "hgw_ip": f.hgw_ip,
            "via_rpi_ip": f.via_rpi_ip,
            "collected_at": f.collected_at,
            "last_seen": f.collected_at,  # Alias pour le frontend
            "manufacturer": f.manufacturer,
            "model_name": f.model_name,
            "serial_number": f.serial_number,
            "software_version": f.software_version,
            "hardware_version": f.hardware_version,
            "external_ip": f.external_ip,
            "uptime_seconds": f.uptime_seconds,
            "mem_free_kb": f.mem_free_kb,
            "mem_total_kb": f.mem_total_kb,
            "device_status": f.device_status,
        })

    return {
        "data": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


from app.services.reconnect_service import ReconnectService

@router.post("/{ip}/reconnect")
def reconnect_hgw(
    ip: str,
    via_rpi_ip: Optional[str] = Query(None, description="RPi IP to use as tunnel (optional)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    try:
        return ReconnectService(db).reconnect_hgw(ip, via_rpi_ip)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HGW reconnect failed: {e}")
    


@router.post("/{ip}/terminal/open")
def open_hgw_terminal(
    ip: str,
    via_rpi_ip: Optional[str] = Query(None, description="Optional. Server auto-selects if omitted."),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    try:
        sess = terminal_manager.open_hgw(db, owner=username, hgw_ip=ip, via_rpi_ip=via_rpi_ip)
        return {
            "session_id": sess.id,
            "device_type": "hgw",
            "hgw_ip": ip,
            "via_rpi_ip": sess.via_rpi_ip,
            "status": sess.status,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{ip}/terminal/sessions")
def list_hgw_terminal_sessions(
    ip: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    return {"data": terminal_manager.list_user_sessions(username, device_type="hgw", target=ip)}

@router.post("/terminal/{session_id}/close")
def close_hgw_terminal_session(
    session_id: str,
    db: Session = Depends(get_db),
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
async def hgw_terminal_ws(websocket: WebSocket, session_id: str):
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
        await websocket.send_text(json.dumps({"type":"status","status":"error","error":"Session not found"}))
        await websocket.close(code=1008)
        return
    if sess.owner != username:
        await websocket.close(code=1008)
        return

    try:
        sess.add_client(websocket)
        sess.start_reader(asyncio.get_running_loop())
        await sess.send_buffer(websocket)
        await websocket.send_text(json.dumps({"type":"status","status":sess.status,"error":sess.error}, ensure_ascii=False))

        while True:
            raw_in = await websocket.receive_text()
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
                await websocket.send_text(json.dumps({"type":"pong"}))
            elif t == "close":
                terminal_manager.force_close(session_id)
                await websocket.close()
                return

    except WebSocketDisconnect:
        pass
    finally:
        try:
            sess.remove_client(websocket)
        except Exception:
            pass