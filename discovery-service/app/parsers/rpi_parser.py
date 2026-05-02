import re
import ipaddress
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# ── Constantes réseau ──────────────────────────────────────────────────────────
EXCLUDED_PREFIXES       = ("127.", "172.", "169.254.")
EXCLUDED_IFACE_PREFIXES = ("lo", "docker", "veth", "br-", "virbr")
IFACE_PRIORITY          = {"eth0": 0, "eth1": 1, "wlan0": 2}


# ── Utilitaires ───────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    """Supprime les séquences ANSI et les retours chariot."""
    text = ANSI_RE.sub("", text or "")
    return text.replace("\r", "").strip()


def _is_valid_ip(ip: str) -> bool:
    """Vérifie qu'une chaîne est une adresse IPv4 valide."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def _is_excluded_iface(name: str) -> bool:
    """Retourne True si l'interface doit être ignorée (lo, docker, veth, br-, virbr)."""
    return any(name.startswith(p) for p in EXCLUDED_IFACE_PREFIXES)


def _is_excluded_ip(ip: str) -> bool:
    """Retourne True si l'IP est exclue (loopback, management, APIPA)."""
    return any(ip.startswith(p) for p in EXCLUDED_PREFIXES)


# ── Parsers système ───────────────────────────────────────────────────────────

def parse_os_release(text: str) -> dict:
    """Parse /etc/os-release content."""
    result = {}
    for line in clean(text).splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"')
        result[key.strip()] = val
    return result


def parse_free_output(text: str) -> dict:
    """
    Parse output of 'free -m'.
    Returns total, used, free in MB.
    """
    result = {}
    for line in clean(text).splitlines():
        if line.lower().startswith("mem:"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    result["total_mb"] = int(parts[1])
                    result["used_mb"]  = int(parts[2])
                    result["free_mb"]  = int(parts[3]) if len(parts) > 3 else None
                except ValueError:
                    pass
    return result


def parse_df_output(text: str) -> dict:
    """
    Parse output of 'df -h' for root filesystem.
    """
    result = {}
    for line in clean(text).splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[5] == "/":
            result["total"]      = parts[1]
            result["used"]       = parts[2]
            result["available"]  = parts[3]
            result["used_pct"]   = parts[4]
            result["filesystem"] = parts[0]
            break
    return result


def parse_temperature(text: str) -> Optional[str]:
    """
    Parse 'vcgencmd measure_temp' output.
    Example: temp=47.8'C  →  "47.8"
    """
    text = clean(text)
    m = re.search(r"temp=([0-9.]+)", text)
    return m.group(1) if m else None


# ── Parsers réseau ────────────────────────────────────────────────────────────

def parse_ip_addr(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse output of 'ip a' to find the best LAN interface.

    Rules:
    - Ignore interfaces : lo, docker*, veth*, br-*, virbr*
    - Ignore IPs        : 127.x.x.x / 172.x.x.x / 169.254.x.x
    - Accept            : toute IP non exclue (192.168.x.x, 10.x.x.x, etc.)

    Priority order: eth0 > eth1 > wlan0 > first found

    Returns: (lan_iface, lan_ip, mac)

    Example:
        ("eth0", "192.168.1.62", "C4:41:1E:FE:8A:53")
        ("eth0", "10.0.1.45",    "B8:27:EB:AA:BB:CC")
    """
    text = clean(text)

    current_iface = None
    current_mac   = None
    candidates    = []

    for line in text.splitlines():
        line = line.strip()

        # ── Nouvelle interface ─────────────────────────────────────────────────
        # Gère : "2: eth0: <...", "2: LAN: <...", "2: LAN@eth0: <..."
        iface_match = re.match(
            r"^\d+:\s+"
            r"([^:@\s]+)"
            r"(?:@[^\s:]+)?"
            r":\s+<",
            line,
        )
        if iface_match:
            name = iface_match.group(1)
            if _is_excluded_iface(name):
                logger.debug("[PARSER] ip a: excluded interface %s", name)
                current_iface = None
            else:
                current_iface = name
            current_mac = None
            continue

        if current_iface is None:
            continue

        # ── MAC address ────────────────────────────────────────────────────────
        mac_match = re.match(r"link/ether\s+([0-9a-f:]{17})", line, re.IGNORECASE)
        if mac_match:
            current_mac = mac_match.group(1).upper()
            continue

        # ── IPv4 ───────────────────────────────────────────────────────────────
        inet_match = re.match(r"inet\s+(\d+\.\d+\.\d+\.\d+)/\d+", line)
        if inet_match:
            ip = inet_match.group(1)

            if _is_excluded_ip(ip):
                logger.debug("[PARSER] ip a: ignored IP %s on %s", ip, current_iface)
                continue

            if not _is_valid_ip(ip):
                logger.debug("[PARSER] ip a: invalid IP %s on %s", ip, current_iface)
                continue

            candidates.append((current_iface, ip, current_mac))
            logger.debug(
                "[PARSER] ip a: candidate → iface=%s ip=%s mac=%s",
                current_iface, ip, current_mac,
            )

    if not candidates:
        logger.warning("[PARSER] ip a: No valid LAN interface found")
        return None, None, None

    # Tri par priorité dynamique (eth0 > eth1 > wlan0 > autres)
    candidates.sort(key=lambda c: IFACE_PRIORITY.get(c[0], 99))
    iface, ip, mac = candidates[0]

    logger.info(
        "[PARSER] ip a: LAN interface selected → %s / %s (mac=%s)",
        iface, ip, mac,
    )
    return iface, ip, mac


def parse_ip_route_dev(text: str) -> Optional[str]:
    """
    Parse output of 'ip r s dev <iface>' to extract the gateway IP.

    Priority:
        1. Line starting with "default via X.X.X.X"
        2. Any line containing "via X.X.X.X"

    Returns validated gateway IP or None.
    """
    text = clean(text)

    if not text:
        logger.debug("[PARSER] ip r s dev: output is empty")
        return None

    logger.debug("[PARSER] ip r s dev output:\n%s", text)

    # ── Priorité 1 : "default via X.X.X.X" ───────────────────────────────────
    for line in text.splitlines():
        m = re.match(r"^default\s+via\s+(\d+\.\d+\.\d+\.\d+)", line.strip())
        if m:
            gw = m.group(1)
            if _is_valid_ip(gw):
                logger.debug("[PARSER] HGW found (default via): %s", gw)
                return gw

    # ── Priorité 2 : n'importe quel "via X.X.X.X" ────────────────────────────
    for line in text.splitlines():
        m = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", line.strip())
        if m:
            gw = m.group(1)
            if _is_valid_ip(gw):
                logger.debug("[PARSER] HGW found (via): %s", gw)
                return gw

    logger.debug("[PARSER] No gateway found in ip r s dev output")
    return None


def detect_hgw(ip_a_text: str, ip_route_text: str) -> dict:
    """
    Fonction de haut niveau combinant parse_ip_addr + parse_ip_route_dev.

    Returns:
        {
            "interface": "eth0",
            "local_ip":  "192.168.1.62",
            "mac":       "C4:41:1E:FE:8A:53",
            "gateway":   "192.168.1.1",
        }
        ou {} si aucune interface valide trouvée.
    """
    iface, ip, mac = parse_ip_addr(ip_a_text)
    if not iface:
        return {}

    gw = parse_ip_route_dev(ip_route_text)
    return {
        "interface": iface,
        "local_ip":  ip,
        "mac":       mac,
        "gateway":   gw,
    }


# ── Parsers processus ─────────────────────────────────────────────────────────

def parse_ps_scripts(text: str) -> tuple[list[str], list[str]]:
    """
    Parse 'ps aux' output to find:
    - Running .sh scripts
    - Running python scripts
    """
    text = clean(text)
    scripts      = []
    python_procs = []

    for line in text.splitlines():
        if "grep" in line or line.strip().startswith("["):
            continue

        if ".sh" in line:
            m = re.search(r"(\S+\.sh(\s+\S+)*)", line)
            if m:
                scripts.append(m.group(0).strip())

        if re.search(r"\bpython[0-9]?\b|\bpython3\b", line, re.IGNORECASE):
            parts  = line.split()
            py_cmd = " ".join(parts[10:]) if len(parts) > 10 else line.strip()
            python_procs.append(py_cmd.strip())

    return list(set(scripts)), list(set(python_procs))


# ── Parsers Docker ────────────────────────────────────────────────────────────

def parse_docker_ps(text: str) -> tuple[bool, list[dict]]:
    """
    Parse 'docker ps -a' output.
    Returns (docker_available, containers_list)
    """
    text = clean(text)

    if "command not found" in text.lower() or "not found" in text.lower():
        return False, []

    containers = []
    lines      = text.splitlines()

    if not lines:
        return True, []

    header = lines[0]
    if "CONTAINER" not in header.upper():
        return True, []

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 6)
        if len(parts) < 7:
            continue

        name_part = parts[6]
        name      = name_part.split()[-1] if name_part else ""

        containers.append({
            "container_id": parts[0],
            "image":        parts[1],
            "command":      parts[2],
            "created":      f"{parts[3]} {parts[4]}",
            "status":       parts[5],
            "name":         name,
        })

    return True, containers


def parse_docker_images(text: str) -> list[dict]:
    """
    Parse 'docker images' output.
    Returns list of images with repository, tag, id, created, size.
    """
    text = clean(text)

    if "command not found" in text.lower():
        return []

    images = []
    lines  = text.splitlines()

    if not lines or "REPOSITORY" not in lines[0].upper():
        return []

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 4)
        if len(parts) >= 5:
            images.append({
                "repository": parts[0],
                "tag":        parts[1],
                "image_id":   parts[2],
                "created":    parts[3],
                "size":       parts[4],
            })

    return images


# ── Parser USB ────────────────────────────────────────────────────────────────

def parse_lsusb(text: str) -> list[str]:
    """Parse 'lsusb' output into list of device strings."""
    text    = clean(text)
    devices = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Bus "):
            devices.append(line)
    return devices