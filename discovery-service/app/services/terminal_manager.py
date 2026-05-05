# app/services/terminal_manager.py
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Set, Deque, Dict, Any
from uuid import uuid4

import paramiko
import telnetlib
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.rpi import Rpi
from app.models.hgw import Hgw
from app.models.switch import Switch

# ── Policy ─────────────────────────────────────────────────────────────
IDLE_TTL_SECONDS = 20 * 60         
INACTIVITY_TTL_SECONDS = 5 * 60     
MAX_SESSIONS_PER_USER = 5
BUFFER_MAX_CHUNKS = 4000

WRITE_ROLES = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def decode_jwt_user(token: str) -> dict:
    """
    WS auth: decode JWT (same secret as discovery service).
    Returns: {"username": ..., "role": ...}
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not username or not role:
            raise JWTError("Invalid token payload")
        if role not in WRITE_ROLES:
            raise JWTError("Write access required")
        return {"username": username, "role": role}
    except JWTError as e:
        raise PermissionError(str(e))


def open_tunnel_sock(tunnel_client: paramiko.SSHClient, host: str, port: int):
    transport = tunnel_client.get_transport()
    if transport is None:
        raise ConnectionError("Tunnel transport not active")
    return transport.open_channel("direct-tcpip", (host, port), ("127.0.0.1", 0))


def ssh_connect_client(
    host: str,
    username: str,
    password: str,
    port: int = 22,
    tunnel: Optional[paramiko.SSHClient] = None,
    timeout: int = 60,
) -> paramiko.SSHClient:
    sock = None
    if tunnel is not None:
        sock = open_tunnel_sock(tunnel, host, port)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        sock=sock,
    )
    return client


def open_pty_shell(client: paramiko.SSHClient, timeout: int = 20) -> paramiko.Channel:
    transport = client.get_transport()
    if transport is None:
        raise ConnectionError("SSH transport not available")
    chan = transport.open_session(timeout=timeout)
    chan.get_pty(term="xterm-256color", width=220, height=60)
    chan.invoke_shell()
    chan.settimeout(0.0)  # non-blocking
    return chan


@dataclass
class BaseTerminalSession:
    id: str
    owner: str
    device_type: str  # rpi|hgw|switch
    target: str       # ip or switch_id

    created_at: datetime = field(default_factory=utcnow)
    last_activity_at: datetime = field(default_factory=utcnow)  # ✅ only updated by input/output

    status: str = "connecting"  # connecting|ready|error|closed
    error: Optional[str] = None

    clients: Set[Any] = field(default_factory=set)  # Set[WebSocket]
    detached_since: Optional[datetime] = None
    buffer: Deque[str] = field(default_factory=lambda: deque(maxlen=BUFFER_MAX_CHUNKS))

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _reader_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _loop: Optional[asyncio.AbstractEventLoop] = field(default=None, repr=False)

    def touch(self):
        """Activity = input/output only."""
        self.last_activity_at = utcnow()

    def attached_count(self) -> int:
        with self._lock:
            return len(self.clients)

    def add_client(self, ws):
        # ✅ attach is NOT considered "activity"
        with self._lock:
            self.clients.add(ws)
            self.detached_since = None

    def remove_client(self, ws):
        # ✅ detach is NOT considered "activity"
        with self._lock:
            self.clients.discard(ws)
            if len(self.clients) == 0:
                self.detached_since = utcnow()

    def push_buffer(self, text: str):
        if text:
            self.buffer.append(text)

    async def send_buffer(self, ws):
        joined = "".join(list(self.buffer))
        await ws.send_text(json.dumps({"type": "buffer", "data": joined}, ensure_ascii=False))

    async def send_to_all(self, payload: dict):
        text = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            targets = list(self.clients)

        dead = []
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)

        if dead:
            with self._lock:
                for ws in dead:
                    self.clients.discard(ws)

    def start_reader(self, loop: asyncio.AbstractEventLoop):
        if self._reader_thread is not None:
            return
        self._loop = loop
        th = threading.Thread(target=self._reader_loop, daemon=True, name=f"term-reader-{self.id[:8]}")
        self._reader_thread = th
        th.start()

    # implemented in subclasses
    def _reader_loop(self): ...
    def send_input(self, data: str): ...
    def resize(self, cols: int, rows: int): ...
    def close(self): ...


@dataclass
class SshTerminalSession(BaseTerminalSession):
    bastion_client: Optional[paramiko.SSHClient] = None
    mid_client: Optional[paramiko.SSHClient] = None     # for HGW: RPi client
    target_client: Optional[paramiko.SSHClient] = None  # RPi/HGW
    channel: Optional[paramiko.Channel] = None

    via_rpi_ip: Optional[str] = None  # only for HGW

    def _reader_loop(self):
        try:
            self.status = "ready"
            self.error = None
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_all({"type": "status", "status": "ready"}),
                    self._loop,
                )

            while not self._stop_event.is_set():
                chan = self.channel
                if chan is None or chan.closed:
                    break

                if chan.recv_ready():
                    data = chan.recv(65535)
                    if not data:
                        time.sleep(0.02)
                        continue

                    text = data.decode("utf-8", errors="ignore")
                    self.push_buffer(text)

                    # ✅ output counts as activity
                    self.touch()

                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self.send_to_all({"type": "output", "data": text}),
                            self._loop,
                        )
                else:
                    time.sleep(0.03)

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_all({"type": "status", "status": "error", "error": str(e)}),
                    self._loop,
                )
        finally:
            if self.status not in ("closed", "error"):
                self.status = "closed"

    def send_input(self, data: str):
        if not data:
            return
        chan = self.channel
        if chan is None or chan.closed:
            raise ConnectionError("Terminal channel closed")
        if len(data) > 8000:
            data = data[:8000]

        chan.send(data)

        # ✅ input counts as activity
        self.touch()

    def resize(self, cols: int, rows: int):
        # ✅ resize does NOT count as activity
        chan = self.channel
        if chan is None or chan.closed:
            return
        try:
            chan.resize_pty(width=int(cols), height=int(rows))
        except Exception:
            pass

    def close(self):
        self.status = "closed"
        self._stop_event.set()

        try:
            if self.channel and not self.channel.closed:
                self.channel.close()
        except Exception:
            pass

        for c in [self.target_client, self.mid_client, self.bastion_client]:
            try:
                if c:
                    c.close()
            except Exception:
                pass

        with self._lock:
            self.clients.clear()


@dataclass
class TelnetTerminalSession(BaseTerminalSession):
    bastion_client: Optional[paramiko.SSHClient] = None
    tn: Optional[telnetlib.Telnet] = None

    def _reader_loop(self):
        try:
            self.status = "ready"
            self.error = None
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_all({"type": "status", "status": "ready"}),
                    self._loop,
                )

            while not self._stop_event.is_set():
                if not self.tn:
                    break
                try:
                    chunk = self.tn.read_very_eager()
                except EOFError:
                    break
                except Exception:
                    chunk = b""

                if chunk:
                    text = chunk.decode("utf-8", errors="ignore")
                    self.push_buffer(text)

                    # ✅ output counts as activity
                    self.touch()

                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self.send_to_all({"type": "output", "data": text}),
                            self._loop,
                        )
                else:
                    time.sleep(0.05)

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_all({"type": "status", "status": "error", "error": str(e)}),
                    self._loop,
                )
        finally:
            if self.status not in ("closed", "error"):
                self.status = "closed"

    def send_input(self, data: str):
        if not data:
            return
        if not self.tn:
            raise ConnectionError("Telnet session closed")
        if len(data) > 8000:
            data = data[:8000]
        self.tn.write(data.encode("utf-8", errors="ignore"))

        # ✅ input counts as activity
        self.touch()

    def resize(self, cols: int, rows: int):
        return

    def close(self):
        self.status = "closed"
        self._stop_event.set()
        try:
            if self.tn:
                self.tn.close()
        except Exception:
            pass
        try:
            if self.bastion_client:
                self.bastion_client.close()
        except Exception:
            pass
        with self._lock:
            self.clients.clear()


class TerminalManager:
    def __init__(self):
        self._sessions: Dict[str, BaseTerminalSession] = {}
        self._user_index: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()
        self._cleanup_started = False

    def start_cleanup(self):
        if self._cleanup_started:
            return
        self._cleanup_started = True
        th = threading.Thread(target=self._cleanup_loop, daemon=True, name="terminal-cleanup")
        th.start()

    def _cleanup_loop(self):
        while True:
            time.sleep(30)
            now = utcnow()
            to_close: list[str] = []

            with self._lock:
                for sid, sess in list(self._sessions.items()):
                    # ✅ NEW: close if no activity for 5 minutes (even if attached)
                    idle_age = (now - sess.last_activity_at).total_seconds()
                    if idle_age >= INACTIVITY_TTL_SECONDS:
                        to_close.append(sid)
                        continue

                    # Old: close if detached too long
                    if sess.detached_since is not None:
                        detached_age = (now - sess.detached_since).total_seconds()
                        if detached_age >= IDLE_TTL_SECONDS:
                            to_close.append(sid)

            for sid in to_close:
                self.force_close(sid)

    def _count_user_sessions(self, username: str) -> int:
        with self._lock:
            return len(self._user_index.get(username, set()))

    def register(self, sess: BaseTerminalSession):
        with self._lock:
            self._sessions[sess.id] = sess
            self._user_index.setdefault(sess.owner, set()).add(sess.id)

    def get(self, session_id: str) -> Optional[BaseTerminalSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_user_sessions(self, username: str, device_type: Optional[str] = None, target: Optional[str] = None) -> list[dict]:
        with self._lock:
            ids = list(self._user_index.get(username, set()))
            sessions = [self._sessions.get(sid) for sid in ids]

        out = []
        for s in sessions:
            if not s:
                continue
            if device_type and s.device_type != device_type:
                continue
            if target and s.target != target:
                continue

            item = {
                "session_id": s.id,
                "device_type": s.device_type,
                "target": s.target,
                "status": s.status,
                "error": s.error,
                "created_at": s.created_at.isoformat(),
                "last_activity_at": s.last_activity_at.isoformat(),
                "attached": s.attached_count(),
            }
            if isinstance(s, SshTerminalSession) and s.device_type == "hgw":
                item["via_rpi_ip"] = s.via_rpi_ip
                item["hgw_ip"] = s.target
            out.append(item)

        out.sort(key=lambda x: x["created_at"], reverse=True)
        return out

    def force_close(self, session_id: str):
        sess = None
        with self._lock:
            sess = self._sessions.pop(session_id, None)
            if sess:
                self._user_index.get(sess.owner, set()).discard(session_id)

        if sess:
            try:
                sess.close()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────
    # Session OPEN (RPi / HGW / Switch)
    # ──────────────────────────────────────────────────────────
    def open_rpi(self, db: Session, owner: str, rpi_ip: str) -> SshTerminalSession:
        if self._count_user_sessions(owner) >= MAX_SESSIONS_PER_USER:
            raise PermissionError("Max sessions per user reached (5). Close a session first.")

        sid = str(uuid4())
        sess = SshTerminalSession(id=sid, owner=owner, device_type="rpi", target=rpi_ip)

        bastion = ssh_connect_client(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        sess.bastion_client = bastion

        chain = self._rpi_creds_chain(db, rpi_ip)
        last_err = None
        rpi_client = None
        for u, p in chain:
            try:
                rpi_client = ssh_connect_client(
                    host=rpi_ip,
                    username=u,
                    password=p,
                    port=22,
                    tunnel=bastion,
                    timeout=60,
                )
                break
            except Exception as e:
                last_err = str(e)
                rpi_client = None

        if rpi_client is None:
            sess.close()
            raise ConnectionError(f"Cannot SSH to RPi {rpi_ip}: {last_err}")

        sess.target_client = rpi_client
        sess.channel = open_pty_shell(rpi_client, timeout=20)

        self.register(sess)
        return sess

    def open_switch(self, db: Session, owner: str, switch_id: int) -> TelnetTerminalSession:
        if self._count_user_sessions(owner) >= MAX_SESSIONS_PER_USER:
            raise PermissionError("Max sessions per user reached (5). Close a session first.")

        sw = db.query(Switch).filter(Switch.id == switch_id).first()
        if not sw:
            raise ValueError("Switch not found")

        sid = str(uuid4())
        sess = TelnetTerminalSession(id=sid, owner=owner, device_type="switch", target=str(switch_id))

        bastion = ssh_connect_client(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        sess.bastion_client = bastion

        transport = bastion.get_transport()
        if transport is None:
            sess.close()
            raise ConnectionError("Bastion transport not active")

        sock = transport.open_channel(
            "direct-tcpip",
            (sw.ip, sw.telnet_port),
            ("127.0.0.1", 0),
        )

        tn = telnetlib.Telnet()
        tn.sock = sock
        tn.rawq = b""
        tn.cookedq = b""
        tn.eof = False
        tn.irawq = 0

        idx, _, _ = tn.expect([b"Username:", b"username:", b"User:", b"login:"], timeout=20)
        if idx == -1:
            sess.close()
            raise ConnectionError("No username prompt received from switch")
        tn.write(sw.telnet_user.encode("ascii", errors="ignore") + b"\n")

        idx2, _, _ = tn.expect([b"Password:", b"password:"], timeout=20)
        if idx2 == -1:
            sess.close()
            raise ConnectionError("No password prompt received from switch")
        tn.write(sw.telnet_pass.encode("ascii", errors="ignore") + b"\n")

        time.sleep(1.0)
        try:
            tn.read_very_eager()
        except Exception:
            pass

        sess.tn = tn
        self.register(sess)
        return sess

    def open_hgw(self, db: Session, owner: str, hgw_ip: str, via_rpi_ip: Optional[str] = None) -> SshTerminalSession:
        if self._count_user_sessions(owner) >= MAX_SESSIONS_PER_USER:
            raise PermissionError("Max sessions per user reached (5). Close a session first.")

        hgw_row = db.query(Hgw).filter(Hgw.serial_number == hgw_ip).first()
        if hgw_row:
            if not via_rpi_ip:
                via_rpi_ip = hgw_row.via_rpi_ip
            hgw_ip = hgw_row.ip

        via = self._auto_select_via_rpi(db, hgw_ip, via_rpi_ip)
        if not via:
            raise ValueError("Cannot auto-select via_rpi_ip for this HGW")

        sid = str(uuid4())
        sess = SshTerminalSession(id=sid, owner=owner, device_type="hgw", target=hgw_ip, via_rpi_ip=via)

        bastion = ssh_connect_client(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        sess.bastion_client = bastion

        chain = self._rpi_creds_chain(db, via)
        last_err = None
        rpi_client = None
        for u, p in chain:
            try:
                rpi_client = ssh_connect_client(
                    host=via,
                    username=u,
                    password=p,
                    port=22,
                    tunnel=bastion,
                    timeout=60,
                )
                break
            except Exception as e:
                last_err = str(e)
                rpi_client = None

        if rpi_client is None:
            sess.close()
            raise ConnectionError(f"Cannot SSH to via_rpi_ip={via}: {last_err}")

        sess.mid_client = rpi_client

        hgw_client = ssh_connect_client(
            host=hgw_ip,
            username=settings.HGW_SSH_USER,
            password=settings.HGW_SSH_PASS,
            port=22,
            tunnel=rpi_client,
            timeout=60,
        )
        sess.target_client = hgw_client
        sess.channel = open_pty_shell(hgw_client, timeout=60)

        self.register(sess)
        return sess

    def _rpi_creds_chain(self, db: Session, rpi_ip: str) -> list[tuple[str, str]]:
        chain: list[tuple[str, str]] = []
        r = db.query(Rpi).filter(Rpi.ip_mgmt == rpi_ip).first()
        if r and r.custom_ssh_user and r.custom_ssh_pass:
            chain.append((r.custom_ssh_user, r.custom_ssh_pass))

        default = (settings.RPI_SSH_USER, settings.RPI_SSH_PASS)
        fallback = (settings.RPI_SSH_FALLBACK_USER, settings.RPI_SSH_FALLBACK_PASS)

        if default not in chain:
            chain.append(default)
        if fallback not in chain:
            chain.append(fallback)
        return chain

    def _auto_select_via_rpi(self, db: Session, hgw_ip: str, via_rpi_ip: Optional[str]) -> Optional[str]:
        if via_rpi_ip:
            return via_rpi_ip

        h = db.query(Hgw).filter(Hgw.ip == hgw_ip).first()
        if h and h.via_rpi_ip:
            return h.via_rpi_ip

        cand = (
            db.query(Rpi)
            .filter(Rpi.hgw_ip == hgw_ip, Rpi.last_ssh_success == True)  # noqa: E712
            .order_by(Rpi.last_seen.desc().nullslast())
            .first()
        )
        if cand:
            return cand.ip_mgmt

        cand2 = (
            db.query(Rpi)
            .filter(Rpi.hgw_ip == hgw_ip)
            .order_by(Rpi.last_seen.desc().nullslast())
            .first()
        )
        if cand2:
            return cand2.ip_mgmt

        return None


terminal_manager = TerminalManager()
terminal_manager.start_cleanup()