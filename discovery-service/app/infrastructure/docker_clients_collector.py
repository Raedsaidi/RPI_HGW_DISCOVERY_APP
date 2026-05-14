# app/infrastructure/docker_clients_collector.py
import re
from typing import Optional

from app.infrastructure.ssh_manager import SSHSession
from app.parsers.rpi_parser import clean


class DockerClientsCollector:
    """
    Collect docker client/peer containers network info via RPi SSH session.
    Compatible with your SSHSession (PTY + invoke_shell).

    Commands used (as requested):
      - docker ps
      - lsusb | grep -i 'NetGear'
      - lsusb | grep -i 'TP-Link'
      - docker exec -it <id> /bin/bash -lc "ifconfig || ip a"
      - docker exec -it <id> /bin/bash -lc "ip r s dev wlanX"
    """

    PREFIXES = ("client", "peer")

    _RE_DEFAULT_VIA = re.compile(r"\bdefault\s+via\s+(\d+\.\d+\.\d+\.\d+)\b", re.IGNORECASE)

    def __init__(self, session: SSHSession):
        self.session = session

    def _sh_single_quote(self, s: str) -> str:
        return "'" + s.replace("'", r"'\''") + "'"

    def _docker_exec_bashlc(self, container_id: str, inner_cmd: str, timeout: int = 25) -> tuple[bool, str]:
        # EXACT style requested, but one-shot (non-blocking)
        quoted = self._sh_single_quote(inner_cmd)
        cmd = f"docker exec -it {container_id} /bin/bash -lc {quoted}"
        ok, out = self.session.execute(cmd, timeout=timeout, idle_timeout=3.0)

        # Some environments may complain about TTY; fallback to -i (still works in your SSHSession)
        low = (out or "").lower()
        if "input device is not a tty" in low or "not a tty" in low:
            cmd2 = f"docker exec -i {container_id} /bin/bash -lc {quoted}"
            return self.session.execute(cmd2, timeout=timeout, idle_timeout=3.0)

        return ok, out

    def _parse_wlan_iface_and_ip(self, raw: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parse output from ifconfig or ip a to find wlanX and inet IPv4.
        Returns (wlan_iface, ip).
        """
        text = clean(raw or "")
        if not text:
            return None, None

        # ifconfig header like: wlan2: flags=...
        re_hdr = re.compile(r"^(wlan\d+):\s", re.IGNORECASE)
        re_inet_ifconfig = re.compile(r"\binet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)\b", re.IGNORECASE)

        current = None
        for line in text.splitlines():
            s = line.strip()
            mh = re_hdr.match(s)
            if mh:
                current = mh.group(1)
                continue

            if current and current.lower().startswith("wlan"):
                mi = re_inet_ifconfig.search(s)
                if mi:
                    return current, mi.group(1)

        # ip a format
        re_iface = re.compile(r"^\d+:\s+(wlan\d+):\s+<", re.IGNORECASE)
        re_inet_ipa = re.compile(r"^\s*inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", re.IGNORECASE)
        current = None
        for line in text.splitlines():
            s = line.rstrip()
            mi = re_iface.match(s.strip())
            if mi:
                current = mi.group(1)
                continue
            if current and current.lower().startswith("wlan"):
                m2 = re_inet_ipa.match(s)
                if m2:
                    return current, m2.group(1)

        return None, None

    def _parse_default_via(self, route_raw: str) -> Optional[str]:
        text = clean(route_raw or "")
        m = self._RE_DEFAULT_VIA.search(text)
        return m.group(1) if m else None

    def collect_usb_wifi_lines(self) -> list[str]:
        """
        Uses EXACT commands requested:
          lsusb |grep -i 'NetGear'
          lsusb |grep -i 'TP-Link'
        """
        lines: list[str] = []

        ok1, out1 = self.session.execute("lsusb |grep -i 'NetGear' || true", timeout=10)
        if ok1 and out1:
            for ln in clean(out1).splitlines():
                ln = ln.strip()
                if ln.startswith("Bus "):
                    lines.append(ln)

        ok2, out2 = self.session.execute("lsusb |grep -i 'TP-Link' || true", timeout=10)
        if ok2 and out2:
            for ln in clean(out2).splitlines():
                ln = ln.strip()
                if ln.startswith("Bus "):
                    lines.append(ln)

        # dedupe preserve order
        seen = set()
        out = []
        for x in lines:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def _parse_docker_ps_table(self, raw: str) -> list[tuple[str, str]]:
        """
        Parse `docker ps` output (table) and return list of (container_id, name),
        filtered by prefixes client*/peer*.
        Robust to shell echo lines and prompts.
        """
        text = clean(raw or "")
        if not text:
            return []

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Remove shell echoes like "docker ps" line itself
        filtered = []
        for ln in lines:
            low = ln.lower()
            if low.startswith("docker ps"):
                continue
            if low.startswith("pi@") and low.endswith("$"):
                continue
            filtered.append(ln)

        # Find header index
        header_idx = None
        for i, ln in enumerate(filtered):
            if "CONTAINER ID" in ln.upper() and "NAMES" in ln.upper():
                header_idx = i
                break
        if header_idx is None:
            return []

        out: list[tuple[str, str]] = []
        for ln in filtered[header_idx + 1 :]:
            parts = ln.split()
            if len(parts) < 2:
                continue
            cid = parts[0].strip()
            name = parts[-1].strip()
            if name.startswith(self.PREFIXES):
                out.append((cid, name))
        return out

    def collect_docker_clients(self) -> tuple[bool, list[dict], Optional[str]]:
        """
        Returns:
          (success, containers_list, error)
        containers_list entries:
          {name, container_id, wlan_iface, ip, hgw_ip}
        """
        ok_ps, ps_raw = self.session.execute("docker ps 2>&1", timeout=20, idle_timeout=3.0)
        text = clean(ps_raw or "")

        if not ok_ps or not text:
            return False, [], "docker ps failed/empty"

        low = text.lower()
        if "docker: command not found" in low or "command not found" in low:
            return False, [], "docker command not found on this RPi"

        targets = self._parse_docker_ps_table(text)

        results: list[dict] = []
        for cid, name in targets:
            ok_net, net_raw = self._docker_exec_bashlc(cid, "ifconfig 2>/dev/null || ip a", timeout=30)
            wlan_iface, ip = self._parse_wlan_iface_and_ip(net_raw if ok_net else "")

            hgw_ip = None
            if wlan_iface:
                ok_r, route_raw = self._docker_exec_bashlc(cid, f"ip r s dev {wlan_iface}", timeout=20)
                if ok_r:
                    hgw_ip = self._parse_default_via(route_raw)

            results.append({
                "name": name,
                "container_id": cid,
                "wlan_iface": wlan_iface,
                "ip": ip,
                "hgw_ip": hgw_ip,
            })

        return True, results, None