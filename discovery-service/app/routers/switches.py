from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
import asyncio
import json
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.core.db import get_db
from app.core.security import require_write_access, require_read_access
from app.repositories.switch_repo import SwitchRepository
from app.schemas.switch import SwitchCreate, SwitchListResponse, SwitchUpdate, SwitchRead
from app.models.switch import Switch
from app.services.terminal_manager import terminal_manager, decode_jwt_user
from app.services.reconnect_service import ReconnectService

router = APIRouter(prefix="/api/v1/switches", tags=["Switches"])


@router.get("", response_model=SwitchListResponse)
def list_switches(
    search: Optional[str] = Query(None, description="Search by IP or name"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    q = db.query(Switch)

    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Switch.ip.ilike(pattern),
                Switch.name.ilike(pattern),
                Switch.mac_address.ilike(pattern),
                Switch.model.ilike(pattern),
            )
        )

    if enabled is not None:
        q = q.filter(Switch.enabled == enabled)

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    switches = (
        q.order_by(Switch.ip.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {"data": switches, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("", response_model=SwitchRead, status_code=201)
def create_switch(
    body: SwitchCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = SwitchRepository(db)
    if repo.get_by_ip(body.ip):
        raise HTTPException(status_code=409, detail=f"Switch {body.ip} already exists.")
    return repo.create(
        ip=body.ip,
        name=body.name,
        telnet_port=body.telnet_port,
        telnet_user=body.telnet_user,
        telnet_pass=body.telnet_pass,
        port_management=body.port_management,
    )


@router.get("/{switch_id}", response_model=SwitchRead)
def get_switch(
    switch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    sw = SwitchRepository(db).get_by_id(switch_id)
    if not sw:
        raise HTTPException(status_code=404, detail="Switch not found.")
    return sw


@router.put("/{switch_id}", response_model=SwitchRead)
def update_switch(
    switch_id: int,
    body: SwitchUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    sw = SwitchRepository(db).update(switch_id, **body.model_dump(exclude_none=True))
    if not sw:
        raise HTTPException(status_code=404, detail="Switch not found.")
    return sw


@router.delete("/{switch_id}")
def delete_switch(
    switch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    if not SwitchRepository(db).delete(switch_id):
        raise HTTPException(status_code=404, detail="Switch not found.")
    return {"message": f"Switch #{switch_id} deleted."}


@router.get("/{switch_id}/rpis")
def get_switch_rpis(
    switch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_read_access),
):
    from app.repositories.rpi_repo import RpiRepository

    sw = SwitchRepository(db).get_by_id(switch_id)
    if not sw:
        raise HTTPException(status_code=404, detail="Switch not found.")
    rpis = RpiRepository(db).list_all()
    return [r for r in rpis if r.switch_ip == sw.ip]


@router.post("/{switch_id}/reconnect")
def reconnect_switch(
    switch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    try:
        return ReconnectService(db).reconnect_switch(switch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Switch reconnect failed: {e}")


# ─────────────────────────────────────────────────────────────
# TERMINAL
# ─────────────────────────────────────────────────────────────
@router.post("/{switch_id}/terminal/open")
def open_switch_terminal(
    switch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    try:
        sess = terminal_manager.open_switch(db, owner=username, switch_id=switch_id)
        return {"session_id": sess.id, "device_type": "switch", "switch_id": switch_id, "status": sess.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{switch_id}/terminal/sessions")
def list_switch_terminal_sessions(
    switch_id: int,
    current_user: dict = Depends(require_write_access),
):
    username = current_user["username"] if isinstance(current_user, dict) else current_user.username
    return {"data": terminal_manager.list_user_sessions(username, device_type="switch", target=str(switch_id))}


@router.post("/terminal/{session_id}/close")
def close_switch_terminal_session(
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
async def switch_terminal_ws(websocket: WebSocket, session_id: str):
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
    if sess.owner != username or sess.device_type != "switch":
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