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
    """

    def __init__(self, session: SSHSession):
        self.session = session

    # ──────────────────────────────────────────────────────────────
    # PRIVATE : Network detection
    # ──────────────────────────────────────────────────────────────

    def _get_lan_and_hgw(
        self, ip_mgmt: str
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
        """
        Step 1 : 'ip a' → select LAN interface
        Step 2 : 'ip r s dev <lan_iface>' → Extract gateway IP (HGW)

        Returns:
            (lan_iface, lan_ip, lan_mac, hgw_ip, raw_ip_addr)
        """

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
            logger.warning("[RPI] %s: '%s' failed → hgw_ip None", ip_mgmt, cmd)
            return lan_iface, lan_ip, lan_mac, None, ipa_raw

        hgw_ip = parse_ip_route_dev(route_raw)
        return lan_iface, lan_ip, lan_mac, hgw_ip, ipa_raw

    def _get_gateway_mac(
        self, ip_mgmt: str, lan_iface: Optional[str], hgw_ip: Optional[str]
    ) -> Optional[str]:
        """
        Get MAC of gateway (hgw_ip) from neighbor table on RPi.
        Uses: ip neigh show <hgw_ip> dev <lan_iface>
        If not present, ping once then retry.
        """
        if not lan_iface or not hgw_ip:
            return None

        cmd = f"ip neigh show {hgw_ip} dev {lan_iface}"
        ok1, neigh_raw1 = self.session.execute(cmd, timeout=5)
        mac = parse_ip_neigh_gateway_mac(neigh_raw1) if ok1 else None
        if mac:
            return mac

        self.session.execute(f"ping -c 1 -W 1 {hgw_ip} >/dev/null 2>&1 || true", timeout=5)
        ok2, neigh_raw2 = self.session.execute(cmd, timeout=5)
        mac = parse_ip_neigh_gateway_mac(neigh_raw2) if ok2 else None
        return mac

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

        # Network
        lan_iface, lan_ip, lan_mac, hgw_ip, raw_ip_addr = self._get_lan_and_hgw(ip_mgmt)
        hgw_gateway_mac = self._get_gateway_mac(ip_mgmt, lan_iface, hgw_ip)
        all_ips = self._build_all_ips(raw_ip_addr)

        # Temperature
        ok_temp, temp_raw = self.session.execute(
            "vcgencmd measure_temp 2>/dev/null || echo ''", timeout=10
        )
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
        # ── Docker (ROBUST) ─────────────────────────────────────────
        docker_avail = False
        containers = []
        images = []

        # 1) Vérifier que docker existe
        ok_docker_bin, docker_bin_raw = self.session.execute(
            "command -v docker >/dev/null 2>&1 && echo ok || echo missing",
            timeout=5,
        )

        if ok_docker_bin and "ok" in (docker_bin_raw or "").lower():

            # 2) Containers — format table natif
            ok_dps, dps_raw = self.session.execute(
                "docker ps -a 2>&1",
                timeout=20,
            )

            logger.debug(
                "[RPI] %s: docker ps raw (ok=%s):\n%s",
                ip_mgmt, ok_dps, (dps_raw or "")[:500],
            )

            if ok_dps:
                docker_usable, containers = parse_docker_ps(dps_raw)
                docker_avail = docker_usable

                if docker_avail:
                    # 3) Images — format table natif
                    ok_img, img_raw = self.session.execute(
                        "docker images 2>&1",
                        timeout=20,
                    )

                    logger.debug(
                        "[RPI] %s: docker images raw (ok=%s):\n%s",
                        ip_mgmt, ok_img, (img_raw or "")[:500],
                    )

                    if ok_img:
                        images = parse_docker_images(img_raw)

        logger.info(
            "[RPI] %s: Docker available=%s → %d containers, %d images",
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

            mac_match = re.match(
                r"link/ether\s+([0-9a-f:]{17})",
                line,
                re.IGNORECASE,
            )
            if mac_match:
                current_mac = mac_match.group(1).upper()
                continue

            inet_match = re.match(
                r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+",
                line,
            )
            if inet_match:
                ip = inet_match.group(1)
                if not ip.startswith("127."):
                    result.append({
                        "iface": current_iface,
                        "ip": ip,
                        "mac": current_mac,
                    })

        return result