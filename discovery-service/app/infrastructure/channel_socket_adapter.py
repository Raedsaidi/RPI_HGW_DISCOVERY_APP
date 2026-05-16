from __future__ import annotations

from typing import Optional


class ChannelSocketAdapter:
    """
    Adapt Paramiko Channel to look like a socket for telnetlib.
    telnetlib needs: recv(), sendall(), close(), settimeout(), fileno().
    """
    def __init__(self, chan):
        self.chan = chan

    def recv(self, n: int) -> bytes:
        return self.chan.recv(n)

    def sendall(self, data: bytes) -> None:
        # telnetlib uses sendall(); Paramiko Channel has send()
        self.chan.send(data)

    def close(self) -> None:
        try:
            self.chan.close()
        except Exception:
            pass

    def settimeout(self, timeout: Optional[float]) -> None:
        try:
            self.chan.settimeout(timeout)
        except Exception:
            pass

    def fileno(self) -> int:
        return self.chan.fileno()