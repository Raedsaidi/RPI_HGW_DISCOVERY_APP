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
        Step 1 : 'ip a'
            → Parse all interfaces
            → Select LAN interface (192.168.x.x, not 127.x / 172.x)

        Step 2 : 'ip r s dev <lan_iface>'
            → Extract default gateway (HGW)
            → HGW = IP after "default via"

        Returns:
            (lan_iface, lan_ip, lan_mac, hgw_ip, raw_ip_addr)

        Example:
            ("eth0", "192.168.1.62", "C4:41:1E:FE:8A:53", "192.168.1.1", "...")
        """

        # ── STEP 1 : ip a ─────────────────────────────────────────
        ok_ipa, ipa_raw = self.session.execute("ip a", timeout=10)

        if not ok_ipa:
            logger.warning("[RPI] %s: 'ip a' command failed", ip_mgmt)
            return None, None, None, None, ""

        lan_iface, lan_ip, lan_mac = parse_ip_addr(ipa_raw)

        if not lan_iface:
            logger.warning(
                "[RPI] %s: No LAN interface found in 'ip a' output "
                "(all IPs excluded or only virtual interfaces present)",
                ip_mgmt,
            )
            return None, None, None, None, ipa_raw

        logger.info(
            "[RPI] %s: LAN interface found → %s / %s (mac=%s)",
            ip_mgmt, lan_iface, lan_ip, lan_mac,
        )

        # ── STEP 2 : ip r s dev <iface> ───────────────────────────
        cmd = f"ip r s dev {lan_iface}"
        ok_route, route_raw = self.session.execute(cmd, timeout=10)

        if not ok_route:
            logger.warning(
                "[RPI] %s: '%s' command failed → hgw_ip will be None",
                ip_mgmt, cmd,
            )
            return lan_iface, lan_ip, lan_mac, None, ipa_raw

        hgw_ip = parse_ip_route_dev(route_raw)

        if hgw_ip is None:
            logger.warning(
                "[RPI] %s: No 'default via' found in '%s' output → hgw_ip=None",
                ip_mgmt, cmd,
            )
        else:
            logger.info(
                "[RPI] %s: HGW (default gateway) = %s",
                ip_mgmt, hgw_ip,
            )

        return lan_iface, lan_ip, lan_mac, hgw_ip, ipa_raw

    # ──────────────────────────────────────────────────────────────
    # PUBLIC : Main collection
    # ──────────────────────────────────────────────────────────────

    def collect_all(self, ip_mgmt: str) -> RpiCollectedData:
        """Collect all metrics from a RPi."""
        logger.info("[RPI] Starting collection for %s", ip_mgmt)

        # ── 1. Hostname ───────────────────────────────────────────
        ok_h, hostname_raw = self.session.execute("hostname", timeout=10)
        hostname = clean(hostname_raw).split("\n")[0].strip() if ok_h else ""

        # ── 2. OS Release ─────────────────────────────────────────
        ok_os, os_raw = self.session.execute(
            "cat /etc/os-release 2>/dev/null", timeout=10
        )
        os_info = parse_os_release(os_raw) if ok_os else {}

        # ── 3. Model ──────────────────────────────────────────────
        ok_model, model_raw = self.session.execute(
            "cat /proc/device-tree/model 2>/dev/null | tr -d '\\0'",
            timeout=10,
        )
        model = clean(model_raw).strip() if ok_model else ""

        # ── 4. Kernel ─────────────────────────────────────────────
        ok_uname, uname_raw = self.session.execute("uname -a", timeout=10)
        kernel = clean(uname_raw).strip() if ok_uname else ""

        # ── 5. Network : LAN iface + HGW ──────────────────────────
        lan_iface, lan_ip, lan_mac, hgw_ip, raw_ip_addr = self._get_lan_and_hgw(
            ip_mgmt
        )

        # ── 5b. Build all_ips ─────────────────────────────────────
        all_ips = self._build_all_ips(raw_ip_addr)

        # ── 6. Temperature ────────────────────────────────────────
        ok_temp, temp_raw = self.session.execute(
            "vcgencmd measure_temp 2>/dev/null || echo ''", timeout=10
        )
        temp = parse_temperature(temp_raw) if ok_temp else None

        # ── 7. Memory ─────────────────────────────────────────────
        ok_mem, mem_raw = self.session.execute("free -m", timeout=10)
        mem = parse_free_output(mem_raw) if ok_mem else {}

        # ── 8. Disk ───────────────────────────────────────────────
        ok_df, df_raw = self.session.execute("df -h", timeout=10)
        disk = parse_df_output(df_raw) if ok_df else {}

        # ── 9. Running processes ───────────────────────────────────
        ok_ps, ps_raw = self.session.execute("ps aux 2>/dev/null", timeout=15)
        scripts, python_procs = parse_ps_scripts(ps_raw) if ok_ps else ([], [])

        # ── 10. Docker ────────────────────────────────────────────
        docker_avail = False
        containers   = []
        images       = []

        ok_docker_test, docker_test_raw = self.session.execute(
            "docker --version 2>/dev/null || echo 'not found'", timeout=5
        )

        if ok_docker_test and "not found" not in docker_test_raw.lower():
            docker_avail = True

            ok_dps, dps_raw = self.session.execute(
                "docker ps -a 2>/dev/null", timeout=15
            )
            if ok_dps:
                _, containers = parse_docker_ps(dps_raw)

            ok_img, img_raw = self.session.execute(
                "docker images 2>/dev/null", timeout=15
            )
            if ok_img:
                images = parse_docker_images(img_raw)

            logger.info(
                "[RPI] %s: Docker → %d containers, %d images",
                ip_mgmt, len(containers), len(images),
            )
        else:
            logger.debug("[RPI] %s: Docker not available", ip_mgmt)

        # ── 11. USB ───────────────────────────────────────────────
        ok_usb, usb_raw = self.session.execute(
            "lsusb 2>/dev/null || echo ''", timeout=10
        )
        usb_devices = parse_lsusb(usb_raw) if ok_usb else []

        # ── Summary log ───────────────────────────────────────────
        logger.info(
            "[RPI] Collected %s → hostname=%s | iface=%s | lan=%s | hgw=%s | temp=%s°C",
            ip_mgmt, hostname, lan_iface, lan_ip, hgw_ip, temp,
        )

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
        """
        Build a list of all IPs from 'ip a' output.

        Handles interface names like:
            - eth0, eth1, wlan0     (standard)
            - LAN, WAN              (custom names)
            - LAN@eth0              (aliased interfaces)

        Returns:
            [
                {"iface": "eth0",  "ip": "192.168.1.62",  "mac": "C4:41:1E:FE:8A:53"},
                {"iface": "eth1",  "ip": "172.16.55.210", "mac": "B8:27:EB:9B:EE:EE"},
                {"iface": "LAN",   "ip": "192.168.2.100", "mac": "3C:18:A0:22:6C:9D"},
            ]
        """
        if not ipa_raw:
            return []

        text          = clean(ipa_raw)
        current_iface = None
        current_mac   = None
        result        = []

        for line in text.splitlines():
            line = line.strip()

            # ── Nouvelle interface ─────────────────────────────────
            # Gère tous les formats :
            #   "2: eth0: <..."
            #   "2: LAN: <..."
            #   "2: LAN@eth0: <..."
            iface_match = re.match(
                r"^\d+:\s+"           # "2: "
                r"([^:@\s]+)"         # nom interface (sans @, :, espace)
                r"(?:@[^\s:]+)?"      # optionnel: "@eth0"
                r":\s+<",             # ": <"
                line
            )
            if iface_match:
                current_iface = iface_match.group(1)
                current_mac   = None
                continue

            # Ignorer loopback
            if current_iface is None or current_iface == "lo":
                continue

            # ── MAC ───────────────────────────────────────────────
            # "link/ether c4:41:1e:fe:8a:53 brd ff:ff:ff:ff:ff:ff"
            mac_match = re.match(
                r"link/ether\s+([0-9a-f:]{17})",
                line,
                re.IGNORECASE,
            )
            if mac_match:
                current_mac = mac_match.group(1).upper()
                continue

            # ── IPv4 ──────────────────────────────────────────────
            # "inet 192.168.1.62/24 brd ..."
            inet_match = re.match(
                r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+",
                line,
            )
            if inet_match:
                ip = inet_match.group(1)
                # Exclure loopback uniquement
                if not ip.startswith("127."):
                    result.append({
                        "iface": current_iface,
                        "ip":    ip,
                        "mac":   current_mac,
                    })

        return result