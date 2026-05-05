import logging
import re
import time
import telnetlib
from typing import Optional, Tuple
import paramiko

logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MORE_RE = re.compile(r"--more--", re.IGNORECASE)
PROMPT_RE = re.compile(r"[>#]\s*$", re.MULTILINE)


def clean_telnet_output(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "")
    # Remove --More-- lines
    text = re.sub(r"--more--", "", text, flags=re.IGNORECASE)
    return text.strip()


class NetgearTelnetSession:
    """
    Persistent Telnet session to a Netgear switch.
    Connects through SSH tunnel (bastion → switch:60000).
    Uses telnetlib with port forwarding.
    """

    def __init__(
        self,
        switch_ip: str,
        switch_port: int,
        username: str,
        password: str,
        bastion_client: paramiko.SSHClient,
        timeout: int = 60,
    ):
        self.switch_ip = switch_ip
        self.switch_port = switch_port
        self.username = username
        self.password = password
        self.bastion_client = bastion_client
        self.timeout = timeout

        self._tn: Optional[telnetlib.Telnet] = None
        self._connected = False
        self._local_socket = None

    @property
    def connected(self) -> bool:
        return self._connected and self._tn is not None

    def connect(self) -> Tuple[bool, str]:
        started = time.perf_counter()
        try:
            logger.info(
                "[TELNET] Connecting to switch %s:%s via bastion tunnel",
                self.switch_ip, self.switch_port,
            )

            # Open SSH tunnel channel to switch
            transport = self.bastion_client.get_transport()
            if transport is None:
                return False, "Bastion transport not active."

            sock = transport.open_channel(
                "direct-tcpip",
                (self.switch_ip, self.switch_port),
                ("127.0.0.1", 0),
            )

            # Wrap paramiko channel in telnetlib
            self._tn = telnetlib.Telnet()
            self._tn.sock = sock
            self._tn.rawq = b""
            self._tn.cookedq = b""
            self._tn.eof = False
            self._tn.irawq = 0

            # Wait for Username prompt
            idx, _, _ = self._tn.expect(
                [b"Username:", b"username:", b"User:"],
                timeout=self.timeout,
            )
            if idx == -1:
                return False, "No username prompt received from switch."

            self._tn.write(self.username.encode("ascii") + b"\n")

            # Wait for Password prompt
            idx2, _, _ = self._tn.expect(
                [b"Password:", b"password:"],
                timeout=self.timeout,
            )
            if idx2 == -1:
                return False, "No password prompt received from switch."

            self._tn.write(self.password.encode("ascii") + b"\n")

            # Wait for switch prompt
            time.sleep(1.5)
            try:
                self._tn.read_very_eager()
            except Exception:
                pass

            self._connected = True
            elapsed = round(time.perf_counter() - started, 2)
            logger.info("[TELNET] Connected to switch %s in %ss", self.switch_ip, elapsed)
            return True, "OK"

        except Exception as e:
            self._cleanup()
            logger.error("[TELNET] Connection failed to %s: %s", self.switch_ip, e)
            return False, str(e)

    def execute(self, command: str, idle_timeout: float = 3.0) -> Tuple[bool, str]:
        """Execute a command on the switch, handling --More-- pagination."""
        if not self.connected:
            ok, msg = self.connect()
            if not ok:
                return False, f"Reconnect failed: {msg}"

        try:
            # Drain buffer
            try:
                self._tn.read_very_eager()
            except Exception:
                pass

            self._tn.write(command.encode("ascii") + b"\n")

            buf = b""
            end_time = time.time() + self.timeout
            last_data = time.time()

            while time.time() < end_time:
                try:
                    chunk = self._tn.read_very_eager()
                except EOFError:
                    self._connected = False
                    break

                if chunk:
                    buf += chunk
                    last_data = time.time()

                    # Handle --More-- pagination
                    if MORE_RE.search(buf.decode("ascii", errors="ignore")):
                        self._tn.write(b"\n")
                        time.sleep(0.2)
                        continue

                    # Check for prompt
                    decoded = buf.decode("ascii", errors="ignore")
                    if PROMPT_RE.search(decoded):
                        # Give a tiny grace period
                        time.sleep(0.3)
                        extra = b""
                        try:
                            extra = self._tn.read_very_eager()
                        except Exception:
                            pass
                        buf += extra
                        break
                else:
                    if buf and (time.time() - last_data) >= idle_timeout:
                        break
                    time.sleep(0.15)

            output = buf.decode("ascii", errors="ignore")
            cleaned = clean_telnet_output(output)
            return True, cleaned

        except Exception as e:
            self._connected = False
            logger.warning("[TELNET] Execute failed on %s: %s", self.switch_ip, e)
            return False, str(e)

    def _cleanup(self):
        try:
            if self._tn:
                self._tn.close()
        except Exception:
            pass
        self._tn = None
        self._connected = False

    def close(self):
        self._cleanup()
        logger.info("[TELNET] Session closed for switch %s", self.switch_ip)

    def __enter__(self):
        ok, msg = self.connect()
        if not ok:
            raise ConnectionError(msg)
        return self

    def __exit__(self, *args):
        self.close()


class HgwTelnetSession:
    """
    Persistent Telnet session to an HGW.
    Connects through SSH tunnel (bastion → RPi → HGW).
    """

    def __init__(
        self,
        hgw_ip: str,
        hgw_port: int,
        username: str,
        password: str,
        tunnel_client: paramiko.SSHClient,
        timeout: int = 60,
    ):
        self.hgw_ip = hgw_ip
        self.hgw_port = hgw_port
        self.username = username
        self.password = password
        self.tunnel_client = tunnel_client
        self.timeout = timeout

        self._tn: Optional[telnetlib.Telnet] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._tn is not None

    def connect(self) -> Tuple[bool, str]:
        started = time.perf_counter()
        try:
            logger.info(
                "[TELNET] Connecting to HGW %s:%s via tunnel",
                self.hgw_ip, self.hgw_port,
            )

            transport = self.tunnel_client.get_transport()
            if transport is None:
                return False, "Tunnel transport not active."

            sock = transport.open_channel(
                "direct-tcpip",
                (self.hgw_ip, self.hgw_port),
                ("127.0.0.1", 0),
            )

            self._tn = telnetlib.Telnet()
            self._tn.sock = sock
            self._tn.rawq = b""
            self._tn.cookedq = b""
            self._tn.eof = False
            self._tn.irawq = 0

            idx, _, _ = self._tn.expect(
                [b"Username:", b"username:", b"User:"],
                timeout=self.timeout,
            )
            if idx == -1:
                return False, "No username prompt received from HGW."

            self._tn.write(self.username.encode("ascii") + b"\n")

            idx2, _, _ = self._tn.expect(
                [b"Password:", b"password:"],
                timeout=self.timeout,
            )
            if idx2 == -1:
                return False, "No password prompt received from HGW."

            self._tn.write(self.password.encode("ascii") + b"\n")

            time.sleep(1.5)
            try:
                self._tn.read_very_eager()
            except Exception:
                pass

            self._connected = True
            elapsed = round(time.perf_counter() - started, 2)
            logger.info("[TELNET] Connected to HGW %s in %ss", self.hgw_ip, elapsed)
            return True, "OK"

        except Exception as e:
            self._cleanup()
            logger.error("[TELNET] Connection failed to HGW %s: %s", self.hgw_ip, e)
            return False, str(e)

    def execute(self, command: str, idle_timeout: float = 3.0) -> Tuple[bool, str]:
        if not self.connected:
            ok, msg = self.connect()
            if not ok:
                return False, f"Reconnect failed: {msg}"

        try:
            try:
                self._tn.read_very_eager()
            except Exception:
                pass

            self._tn.write(command.encode("ascii") + b"\n")

            buf = b""
            end_time = time.time() + self.timeout
            last_data = time.time()

            while time.time() < end_time:
                try:
                    chunk = self._tn.read_very_eager()
                except EOFError:
                    self._connected = False
                    break

                if chunk:
                    buf += chunk
                    last_data = time.time()

                    if MORE_RE.search(buf.decode("ascii", errors="ignore")):
                        self._tn.write(b"\n")
                        time.sleep(0.2)
                        continue

                    decoded = buf.decode("ascii", errors="ignore")
                    if PROMPT_RE.search(decoded):
                        time.sleep(0.3)
                        extra = b""
                        try:
                            extra = self._tn.read_very_eager()
                        except Exception:
                            pass
                        buf += extra
                        break
                else:
                    if buf and (time.time() - last_data) >= idle_timeout:
                        break
                    time.sleep(0.15)

            output = buf.decode("ascii", errors="ignore")
            cleaned = clean_telnet_output(output)
            return True, cleaned

        except Exception as e:
            self._connected = False
            logger.warning("[TELNET] Execute failed on HGW %s: %s", self.hgw_ip, e)
            return False, str(e)

    def _cleanup(self):
        try:
            if self._tn:
                self._tn.close()
        except Exception:
            pass
        self._tn = None
        self._connected = False

    def close(self):
        self._cleanup()
        logger.info("[TELNET] Session closed for HGW %s", self.hgw_ip)

    def __enter__(self):
        ok, msg = self.connect()
        if not ok:
            raise ConnectionError(msg)
        return self

    def __exit__(self, *args):
        self.close()


class TelnetPool:
    """Pool of persistent Telnet sessions keyed by switch IP."""

    def __init__(self):
        self._sessions: dict[str, NetgearTelnetSession] = {}

    def get_or_create(
        self,
        switch_ip: str,
        switch_port: int,
        username: str,
        password: str,
        bastion_client: paramiko.SSHClient,
        timeout: int = 40,
    ) -> NetgearTelnetSession:
        if switch_ip not in self._sessions:
            sess = NetgearTelnetSession(
                switch_ip=switch_ip,
                switch_port=switch_port,
                username=username,
                password=password,
                bastion_client=bastion_client,
                timeout=timeout,
            )
            self._sessions[switch_ip] = sess
        return self._sessions[switch_ip]

    def close_all(self):
        for sess in self._sessions.values():
            try:
                sess.close()
            except Exception:
                pass
        self._sessions.clear()