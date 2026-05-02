import logging
import time
import socket
import re
from typing import Optional, Tuple
import paramiko

logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class SSHSession:
    """
    Persistent SSH session using Paramiko shell.
    Supports tunneling through a bastion host.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        tunnel: Optional[paramiko.SSHClient] = None,
        timeout: int = 15,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.tunnel = tunnel
        self.timeout = timeout

        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._channel is not None and not self._channel.closed

    def connect(self) -> Tuple[bool, str]:
        started = time.perf_counter()
        try:
            logger.info(
                "[SSH] Connecting to %s:%s (user=%s, tunnel=%s)",
                self.host, self.port, self.username,
                self.tunnel is not None,
            )

            sock = None
            if self.tunnel:
                transport = self.tunnel.get_transport()
                if transport is None:
                    return False, "Tunnel transport is not active."
                sock = transport.open_channel(
                    "direct-tcpip",
                    (self.host, self.port),
                    ("127.0.0.1", 0),
                )

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
                sock=sock,
            )

            transport = client.get_transport()
            chan = transport.open_session(timeout=self.timeout)
            chan.get_pty(term="vt100", width=220, height=50)
            chan.invoke_shell()
            chan.settimeout(self.timeout)

            time.sleep(1.5)
            # Drain initial banner
            try:
                if chan.recv_ready():
                    chan.recv(65535)
            except Exception:
                pass

            self._client = client
            self._channel = chan
            self._connected = True

            elapsed = round(time.perf_counter() - started, 2)
            logger.info("[SSH] Connected to %s in %ss", self.host, elapsed)
            return True, "OK"

        except paramiko.AuthenticationException:
            return False, f"Authentication failed for {self.username}@{self.host}"
        except (socket.timeout, TimeoutError):
            return False, f"Connection timeout to {self.host}:{self.port}"
        except paramiko.SSHException as e:
            return False, f"SSH error: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def execute(
        self,
        command: str,
        timeout: int = 30,
        idle_timeout: float = 2.0,
    ) -> Tuple[bool, str]:
        """Execute a command on the persistent shell."""
        if not self.connected:
            ok, msg = self.connect()
            if not ok:
                return False, f"Reconnect failed: {msg}"

        try:
            # Drain any pending data
            self._drain(0.3)

            self._channel.send(command + "\n")
            time.sleep(0.2)

            output = self._read_until_idle(timeout=timeout, idle_timeout=idle_timeout)
            cleaned = self._clean(output)
            return True, cleaned

        except Exception as e:
            self._connected = False
            logger.warning("[SSH] Execute failed on %s: %s", self.host, e)
            return False, str(e)

    def _drain(self, max_seconds: float = 0.5):
        end = time.time() + max_seconds
        while time.time() < end:
            if self._channel and self._channel.recv_ready():
                try:
                    self._channel.recv(65535)
                except Exception:
                    return
            time.sleep(0.05)

    def _read_until_idle(self, timeout: int = 30, idle_timeout: float = 2.0) -> str:
        """Read until no data received for idle_timeout seconds."""
        end = time.time() + timeout
        last_data = time.time()
        chunks = []

        while time.time() < end:
            if self._channel.closed:
                break
            try:
                if self._channel.recv_ready():
                    data = self._channel.recv(65535)
                    if data:
                        decoded = data.decode("utf-8", errors="ignore")
                        chunks.append(decoded)
                        last_data = time.time()
                else:
                    if chunks and (time.time() - last_data) >= idle_timeout:
                        break
                    time.sleep(0.1)
            except socket.timeout:
                if chunks and (time.time() - last_data) >= idle_timeout:
                    break
            except Exception as e:
                logger.debug("[SSH] Read error on %s: %s", self.host, e)
                break

        return "".join(chunks)

    def _clean(self, text: str) -> str:
        text = ANSI_RE.sub("", text)
        text = text.replace("\r", "")
        return text.strip()

    def close(self):
        try:
            if self._channel and not self._channel.closed:
                self._channel.close()
        except Exception:
            pass
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._connected = False
        self._channel = None
        self._client = None

    def __enter__(self):
        ok, msg = self.connect()
        if not ok:
            raise ConnectionError(msg)
        return self

    def __exit__(self, *args):
        self.close()


class SSHPool:
    """
    Pool of persistent SSH sessions.
    Key: (host, port, username, password, tunnel_id)
    """

    def __init__(self):
        self._sessions: dict[tuple, SSHSession] = {}

    def get_or_create(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        tunnel: Optional[paramiko.SSHClient] = None,
        timeout: int = 15,
    ) -> SSHSession:
        tunnel_id = id(tunnel) if tunnel is not None else None
        key = (host, port, username, password, tunnel_id)

        if key not in self._sessions:
            sess = SSHSession(
                host=host,
                username=username,
                password=password,
                port=port,
                tunnel=tunnel,
                timeout=timeout,
            )
            self._sessions[key] = sess

        return self._sessions[key]

    def close_all(self):
        for sess in self._sessions.values():
            try:
                sess.close()
            except Exception:
                pass
        self._sessions.clear()