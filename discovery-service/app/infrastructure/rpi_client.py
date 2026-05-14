# app/infrastructure/rpi_client.py
import json
import re
import logging
from dataclasses import dataclass
from typing import Optional

from app.infrastructure.ssh_manager import SSHSession
from app.parsers.rpi_parser import (
    parse_os_release,
    parse_free_output,
    parse_df_output,
    parse_temperature,
    parse_ip_addr,
    parse_ip_route_dev,
    parse_ip_neigh_gateway_mac,
    parse_ps_scripts,
    parse_docker_ps,
    parse_docker_images,
    parse_lsusb,
    clean,
)

logger = logging.getLogger(__name__)


@dataclass
class RpiCollectedData:
    ip_mgmt: str
    hostname: str = ""
    os_name: str = ""
    os_version: str = ""
    os_pretty: str = ""
    model: str = ""
    kernel: str = ""

    # Network
    lan_iface: Optional[str] = None
    lan_ip: Optional[str] = None
    lan_mac: Optional[str] = None
    hgw_ip: Optional[str] = None

    # MAC de la gateway (vue depuis le RPi)
    hgw_gateway_mac: Optional[str] = None

    all_ips: str = "[]"

    # Metrics
    temp_celsius: Optional[str] = None
    mem_total_mb: Optional[int] = None
    mem_used_mb: Optional[int] = None
    mem_free_mb: Optional[int] = None
    disk_total: Optional[str] = None
    disk_used: Optional[str] = None
    disk_used_pct: Optional[str] = None

    # Processes
    running_scripts: str = "[]"
    running_python: str = "[]"

    # Docker
    docker_available: bool = False
    docker_containers: str = "[]"
    docker_images: str = "[]"

    # USB
    usb_devices: str = "[]"

    # Raw
    raw_ip_addr: str = ""
    raw_ps: str = ""

    success: bool = True
    error: Optional[str] = None


class RpiClient:
    """
    High-level client for collecting data from a Raspberry Pi
    using a persistent SSH session.

    HGW detection fallback chain:
      1) ip a -> parse LAN iface -> ip r s dev <iface> -> default via <HGW>
      2) ip neigh -> find IPv6 "router" MAC -> match same MAC on IPv4 -> <HGW>
      3) docker clients/peers -> docker ps -> per container:
           docker exec -it <id> /bin/bash -lc "ifconfig || ip a"
           find wlanX -> docker exec -it <id> /bin/bash -lc "ip r s dev wlanX"
    """

    # Container name prefixes to inspect in method (3)
    DOCKER_CLIENT_PREFIXES = ("client", "peer")

    # Keywords to count wifi dongles lines in lsusb (logs only)
    WIFI_USB_KEYWORDS = ("netgear", "tp-link")

    def __init__(self, session: SSHSession):
        self.session = session

    # ──────────────────────────────────────────────────────────────
    # Method 1: ip a + ip route
    # ──────────────────────────────────────────────────────────────

    def _get_lan_and_hgw(
        self, ip_mgmt: str
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
        ok_ipa, ipa_raw = self.session.execute("ip a", timeout=10)
        if not ok_ipa:
            logger.warning("[RPI] %s: 'ip a' command failed", ip_mgmt)
            return None, None, None, None, ""

        lan_iface, lan_ip, lan_mac = parse_ip_addr(ipa_raw)

        if not lan_iface:
            logger.warning("[RPI] %s: No LAN interface found in 'ip a' output", ip_mgmt)
            return None, None, None, None, ipa_raw

        cmd = f"ip r s dev {lan_iface}"
        ok_route, route_raw = self.session.execute(cmd, timeout=10)
        if not ok_route:
            logger.warning("[RPI] %s: '%s' failed -> hgw_ip None", ip_mgmt, cmd)
            return lan_iface, lan_ip, lan_mac, None, ipa_raw

        hgw_ip = parse_ip_route_dev(route_raw)
        return lan_iface, lan_ip, lan_mac, hgw_ip, ipa_raw

    # ──────────────────────────────────────────────────────────────
    # Method 2: ip neigh (router MAC correlation)
    # ──────────────────────────────────────────────────────────────

    _RE_NEIGH_V6_ROUTER = re.compile(
        r"(?P<ip6>fe80::[0-9a-f:]+)\s+dev\s+(?P<dev>\S+)\s+lladdr\s+(?P<mac>[0-9a-f:]{17})\s+.*\brouter\b",
        re.IGNORECASE,
    )
    _RE_NEIGH_V4 = re.compile(
        r"(?P<ip4>\d+\.\d+\.\d+\.\d+)\s+dev\s+(?P<dev>\S+)\s+lladdr\s+(?P<mac>[0-9a-f:]{17})\b",
        re.IGNORECASE,
    )

    def _get_hgw_from_ip_neigh(self, ip_mgmt: str) -> tuple[Optional[str], Optional[str]]:
        ok, neigh_raw = self.session.execute("ip neigh", timeout=10)
        if not ok or not (neigh_raw or "").strip():
            return None, None

        text = clean(neigh_raw)
        router_match = self._RE_NEIGH_V6_ROUTER.search(text)
        if not router_match:
            return None, None

        router_mac = (router_match.group("mac") or "").upper()
        router_dev = router_match.group("dev")

        v4_candidates: list[tuple[str, str]] = []
        for m in self._RE_NEIGH_V4.finditer(text):
            mac = (m.group("mac") or "").upper()
            if mac == router_mac:
                v4_candidates.append((m.group("ip4"), m.group("dev")))

        if not v4_candidates:
            return None, router_dev

        # prefer same dev, then .1, else first
        same_dev = [ip for ip, dev in v4_candidates if dev == router_dev]
        candidates = same_dev if same_dev else [ip for ip, _ in v4_candidates]
        prefer_dot1 = [ip for ip in candidates if ip.endswith(".1")]
        chosen = prefer_dot1[0] if prefer_dot1 else candidates[0]

        logger.info(
            "[RPI] %s: HGW resolved by method2(ip neigh): router_mac=%s dev=%s -> hgw_ip=%s",
            ip_mgmt, router_mac, router_dev, chosen
        )
        return chosen, router_dev

    # ──────────────────────────────────────────────────────────────
    # Method 3: docker clients/peers (client* + peer*)
    # Commands are "100%" compatible with your SSHSession:
    # - docker ps
    # - lsusb
    # - docker exec -it <id> /bin/bash -lc "<cmd>" (never interactive shell alone)
    # ──────────────────────────────────────────────────────────────

    _RE_DEFAULT_VIA = re.compile(r"\bdefault\s+via\s+(?P<gw>\d+\.\d+\.\d+\.\d+)\b", re.IGNORECASE)

    def _sh_single_quote(self, s: str) -> str:
        """Safely wrap string for /bin/bash -lc '...'."""
        return "'" + s.replace("'", r"'\''") + "'"

    def _docker_exec_bashlc(self, container_id: str, inner_cmd: str, timeout: int = 25) -> tuple[bool, str]:
        """
        Equivalent to:
          docker exec -it <id> /bin/bash
          <inner_cmd>
          exit
        But one-shot:
          docker exec -it <id> /bin/bash -lc '<inner_cmd>'
        """
        quoted = self._sh_single_quote(inner_cmd)

        # Primary: like you want: -it + /bin/bash
        cmd1 = f"docker exec -it {container_id} /bin/bash -lc {quoted}"
        ok1, out1 = self.session.execute(cmd1, timeout=timeout, idle_timeout=3.0)
        if ok1 and out1 is not None:
            return ok1, out1

        # Fallback A: sometimes -t can fail in weird environments (safe fallback)
        cmd2 = f"docker exec -i {container_id} /bin/bash -lc {quoted}"
        ok2, out2 = self.session.execute(cmd2, timeout=timeout, idle_timeout=3.0)
        if ok2 and out2 is not None:
            return ok2, out2

        # Fallback B: if bash missing in container
        cmd3 = f"docker exec -it {container_id} /bin/sh -lc {quoted}"
        ok3, out3 = self.session.execute(cmd3, timeout=timeout, idle_timeout=3.0)
        if ok3 and out3 is not None:
            return ok3, out3

        cmd4 = f"docker exec -i {container_id} /bin/sh -lc {quoted}"
        ok4, out4 = self.session.execute(cmd4, timeout=timeout, idle_timeout=3.0)
        return ok4, out4

    def _parse_wlan_ifaces_from_ifconfig(self, raw: str) -> list[dict]:
        """
        Returns list of dicts: [{"iface": "wlan2", "ip": "192.168.1.163"}, ...]
        Robust to prompts/echo: we only parse real ifconfig blocks.
        """
        text = clean(raw or "")
        if not text:
            return []

        # Detect interface header lines like: "wlan2: flags=..."
        # Also supports older format: "wlan0     Link encap:Ethernet ..."
        re_hdr1 = re.compile(r"^(?P<iface>[A-Za-z0-9_.:-]+):\s+flags=", re.IGNORECASE)
        re_hdr2 = re.compile(r"^(?P<iface>[A-Za-z0-9_.:-]+)\s+Link\s+encap:", re.IGNORECASE)
        re_inet = re.compile(r"\binet\s+(?:addr:)?(?P<ip>\d+\.\d+\.\d+\.\d+)\b")

        current = None
        results: list[dict] = []
        for line in text.splitlines():
            line_s = line.strip()

            m = re_hdr1.match(line_s) or re_hdr2.match(line_s)
            if m:
                current = m.group("iface")
                continue

            if not current:
                continue

            if not current.lower().startswith("wlan"):
                continue

            mi = re_inet.search(line_s)
            if mi:
                ip = mi.group("ip")
                if ip and not ip.startswith("127."):
                    # avoid duplicates
                    if not any(r["iface"] == current and r.get("ip") == ip for r in results):
                        results.append({"iface": current, "ip": ip})

        return results

    def _parse_wlan_ifaces_from_ip_a(self, raw: str) -> list[dict]:
        """
        Returns list of dicts: [{"iface": "wlan2", "ip": "192.168.1.163"}, ...]
        """
        text = clean(raw or "")
        if not text:
            return []

        re_iface = re.compile(r"^\d+:\s+(?P<iface>[^:@\s]+)(?:@[^\s:]+)?:\s+<", re.IGNORECASE)
        re_inet = re.compile(r"^\s*inet\s+(?P<ip>\d+\.\d+\.\d+\.\d+)/\d+", re.IGNORECASE)

        current = None
        results: list[dict] = []
        for line in text.splitlines():
            line_r = line.rstrip()

            m = re_iface.match(line_r.strip())
            if m:
                current = m.group("iface")
                continue

            if not current or not current.lower().startswith("wlan"):
                continue

            mi = re_inet.match(line_r)
            if mi:
                ip = mi.group("ip")
                if ip and not ip.startswith("127."):
                    if not any(r["iface"] == current and r.get("ip") == ip for r in results):
                        results.append({"iface": current, "ip": ip})

        return results

    def _get_hgw_from_docker_clients(self, ip_mgmt: str) -> Optional[str]:
        # 1) docker ps
        ok_ps, docker_ps_raw = self.session.execute("docker ps 2>&1", timeout=20, idle_timeout=3.0)
        if not ok_ps or not (docker_ps_raw or "").strip():
            return None

        docker_usable, containers = parse_docker_ps(docker_ps_raw)
        if not docker_usable:
            return None

        # Filter by prefixes client*/peer*
        targets = []
        for c in containers:
            cid = (c.get("container_id") or "").strip()
            name = (c.get("name") or "").strip()
            if not cid or not name:
                continue
            if name.startswith(self.DOCKER_CLIENT_PREFIXES):
                targets.append({"id": cid, "name": name})

        logger.info(
            "[RPI] %s: method3 docker targets prefixes=%s -> %d containers: %s",
            ip_mgmt, list(self.DOCKER_CLIENT_PREFIXES), len(targets),
            [t["name"] for t in targets],
        )

        if not targets:
            return None

        # 2) lsusb (logs only)
        ok_usb, usb_raw = self.session.execute("lsusb 2>/dev/null || echo ''", timeout=10, idle_timeout=2.5)
        if ok_usb and usb_raw:
            usb_lines = [ln.strip() for ln in clean(usb_raw).splitlines() if ln.strip()]
            wifi_lines = [ln for ln in usb_lines if any(k in ln.lower() for k in self.WIFI_USB_KEYWORDS)]
            logger.info(
                "[RPI] %s: method3 lsusb wifi_lines=%d keywords=%s sample=%s",
                ip_mgmt, len(wifi_lines), list(self.WIFI_USB_KEYWORDS), wifi_lines[:5],
            )

        # 3) Inspect each container -> list ALL wlan ifaces, ips, gateways
        all_details: list[dict] = []
        gw_candidates: list[str] = []

        for t in targets:
            cid = t["id"]
            name = t["name"]

            ok_net, net_raw = self._docker_exec_bashlc(cid, "ifconfig 2>/dev/null || ip a", timeout=30)
            if not ok_net or not (net_raw or "").strip():
                all_details.append({"name": name, "id": cid, "wlan": [], "error": "cannot_read_net"})
                continue

            # Parse wlan ifaces and their IPs (try ifconfig parse first; fallback to ip a parse)
            wlan_list = self._parse_wlan_ifaces_from_ifconfig(net_raw)
            if not wlan_list:
                wlan_list = self._parse_wlan_ifaces_from_ip_a(net_raw)

            # For each wlan iface, find gateway via ip route dev wlanX
            wlan_infos = []
            for w in wlan_list:
                iface = w.get("iface")
                ip = w.get("ip")
                gw = None

                if iface:
                    ok_r, route_raw = self._docker_exec_bashlc(cid, f"ip r s dev {iface}", timeout=20)
                    if ok_r and route_raw:
                        m = self._RE_DEFAULT_VIA.search(clean(route_raw))
                        if m:
                            gw = m.group("gw")

                wlan_infos.append({"iface": iface, "ip": ip, "gw": gw})
                if gw:
                    gw_candidates.append(gw)

            all_details.append({"name": name, "id": cid, "wlan": wlan_infos})

        # Log: afficher toutes les adresses trouvées (comme tu as demandé)
        logger.info("[RPI] %s: method3 docker wlan details=%s", ip_mgmt, all_details)

        if not gw_candidates:
            return None

        uniq = sorted(set(gw_candidates))
        if len(uniq) == 1:
            chosen = uniq[0]
            logger.info("[RPI] %s: HGW resolved by method3(docker)=%s", ip_mgmt, chosen)
            return chosen

        # If multiple gateways: pick most common, log warning with all candidates
        counts = {gw: gw_candidates.count(gw) for gw in uniq}
        max_count = max(counts.values())
        winners = [gw for gw, c in counts.items() if c == max_count]
        chosen = None
        for gw in gw_candidates:
            if gw in winners:
                chosen = gw
                break
        chosen = chosen or gw_candidates[0]

        logger.warning(
            "[RPI] %s: method3 multiple gateway candidates uniq=%s counts=%s -> chosen=%s",
            ip_mgmt, uniq, counts, chosen
        )
        return chosen

    # ──────────────────────────────────────────────────────────────
    # Gateway MAC (works even if lan_iface unknown)
    # ──────────────────────────────────────────────────────────────

    _RE_ANY_LLADDR = re.compile(r"\blladdr\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", re.IGNORECASE)

    def _get_gateway_mac(
        self, ip_mgmt: str, lan_iface: Optional[str], hgw_ip: Optional[str]
    ) -> Optional[str]:
        if not hgw_ip:
            return None

        def _read_neigh() -> Optional[str]:
            if lan_iface:
                cmd = f"ip neigh show {hgw_ip} dev {lan_iface}"
            else:
                cmd = f"ip neigh show {hgw_ip}"
            ok, neigh_raw = self.session.execute(cmd, timeout=6)
            if not ok:
                return None

            mac = parse_ip_neigh_gateway_mac(neigh_raw)
            if mac:
                return mac

            txt = clean(neigh_raw or "")
            m = self._RE_ANY_LLADDR.search(txt)
            return m.group(1).upper() if m else None

        mac = _read_neigh()
        if mac:
            return mac

        self.session.execute(f"ping -c 1 -W 1 {hgw_ip} >/dev/null 2>&1 || true", timeout=6)
        return _read_neigh()

    # ──────────────────────────────────────────────────────────────
    # PUBLIC : Main collection
    # ──────────────────────────────────────────────────────────────

    def collect_all(self, ip_mgmt: str) -> RpiCollectedData:
        logger.info("[RPI] Starting collection for %s", ip_mgmt)

        ok_h, hostname_raw = self.session.execute("hostname", timeout=10)
        hostname = clean(hostname_raw).split("\n")[0].strip() if ok_h else ""

        ok_os, os_raw = self.session.execute("cat /etc/os-release 2>/dev/null", timeout=10)
        os_info = parse_os_release(os_raw) if ok_os else {}

        ok_model, model_raw = self.session.execute(
            "cat /proc/device-tree/model 2>/dev/null | tr -d '\\0'",
            timeout=10,
        )
        model = clean(model_raw).strip() if ok_model else ""

        ok_uname, uname_raw = self.session.execute("uname -a", timeout=10)
        kernel = clean(uname_raw).strip() if ok_uname else ""

        # ── Network + HGW fallback chain ─────────────────────────────
        lan_iface, lan_ip, lan_mac, hgw_ip, raw_ip_addr = self._get_lan_and_hgw(ip_mgmt)
        method_used = "method1"

        # Method2
        if not hgw_ip:
            hgw2, dev2 = self._get_hgw_from_ip_neigh(ip_mgmt)
            if hgw2:
                hgw_ip = hgw2
                # if method1 failed to pick iface, keep a best-effort dev name
                if not lan_iface and dev2:
                    lan_iface = dev2
                method_used = "method2"

        # Method3
        if not hgw_ip:
            hgw3 = self._get_hgw_from_docker_clients(ip_mgmt)
            if hgw3:
                hgw_ip = hgw3
                method_used = "method3"

        if hgw_ip:
            logger.info("[RPI] %s: HGW resolved=%s via %s", ip_mgmt, hgw_ip, method_used)
        else:
            logger.warning("[RPI] %s: HGW not resolved (all methods failed)", ip_mgmt)

        hgw_gateway_mac = self._get_gateway_mac(ip_mgmt, lan_iface, hgw_ip)
        all_ips = self._build_all_ips(raw_ip_addr)

        # Temperature
        ok_temp, temp_raw = self.session.execute("vcgencmd measure_temp 2>/dev/null || echo ''", timeout=10)
        temp = parse_temperature(temp_raw) if ok_temp else None

        # Memory
        ok_mem, mem_raw = self.session.execute("free -m", timeout=10)
        mem = parse_free_output(mem_raw) if ok_mem else {}

        # Disk
        ok_df, df_raw = self.session.execute("df -h", timeout=10)
        disk = parse_df_output(df_raw) if ok_df else {}

        # PS
        ok_ps, ps_raw = self.session.execute("ps aux 2>/dev/null", timeout=15)
        scripts, python_procs = parse_ps_scripts(ps_raw) if ok_ps else ([], [])

        # ── Docker inventory (existing) ─────────────────────────────
        docker_avail = False
        containers = []
        images = []

        ok_docker_bin, docker_bin_raw = self.session.execute(
            "command -v docker >/dev/null 2>&1 && echo ok || echo missing",
            timeout=5,
        )

        if ok_docker_bin and "ok" in (docker_bin_raw or "").lower():
            ok_dps, dps_raw = self.session.execute("docker ps -a 2>&1", timeout=20, idle_timeout=3.0)
            if ok_dps:
                docker_usable, containers = parse_docker_ps(dps_raw)
                docker_avail = docker_usable
                if docker_avail:
                    ok_img, img_raw = self.session.execute("docker images 2>&1", timeout=20, idle_timeout=3.0)
                    if ok_img:
                        images = parse_docker_images(img_raw)

        logger.info(
            "[RPI] %s: Docker available=%s -> %d containers, %d images",
            ip_mgmt, docker_avail, len(containers), len(images),
        )

        # USB
        ok_usb, usb_raw = self.session.execute("lsusb 2>/dev/null || echo ''", timeout=10)
        usb_devices = parse_lsusb(usb_raw) if ok_usb else []

        return RpiCollectedData(
            ip_mgmt=ip_mgmt,
            hostname=hostname,
            os_name=os_info.get("NAME", ""),
            os_version=os_info.get("VERSION_ID", ""),
            os_pretty=os_info.get("PRETTY_NAME", ""),
            model=model,
            kernel=kernel,
            lan_iface=lan_iface,
            lan_ip=lan_ip,
            lan_mac=lan_mac,
            hgw_ip=hgw_ip,
            hgw_gateway_mac=hgw_gateway_mac,
            all_ips=json.dumps(all_ips),
            temp_celsius=temp,
            mem_total_mb=mem.get("total_mb"),
            mem_used_mb=mem.get("used_mb"),
            mem_free_mb=mem.get("free_mb"),
            disk_total=disk.get("total"),
            disk_used=disk.get("used"),
            disk_used_pct=disk.get("used_pct"),
            running_scripts=json.dumps(scripts),
            running_python=json.dumps(python_procs),
            docker_available=docker_avail,
            docker_containers=json.dumps(containers),
            docker_images=json.dumps(images),
            usb_devices=json.dumps(usb_devices),
            raw_ip_addr=raw_ip_addr,
            raw_ps=ps_raw if ok_ps else "",
            success=True,
        )

    def _build_all_ips(self, ipa_raw: str) -> list[dict]:
        if not ipa_raw:
            return []

        text = clean(ipa_raw)
        current_iface = None
        current_mac = None
        result = []

        for line in text.splitlines():
            line = line.strip()

            iface_match = re.match(
                r"^\d+:\s+"
                r"([^:@\s]+)"
                r"(?:@[^\s:]+)?"
                r":\s+<",
                line
            )
            if iface_match:
                current_iface = iface_match.group(1)
                current_mac = None
                continue

            if current_iface is None or current_iface == "lo":
                continue

            mac_match = re.match(r"link/ether\s+([0-9a-f:]{17})", line, re.IGNORECASE)
            if mac_match:
                current_mac = mac_match.group(1).upper()
                continue

            inet_match = re.match(r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", line)
            if inet_match:
                ip = inet_match.group(1)
                if not ip.startswith("127."):
                    result.append({"iface": current_iface, "ip": ip, "mac": current_mac})

        return result