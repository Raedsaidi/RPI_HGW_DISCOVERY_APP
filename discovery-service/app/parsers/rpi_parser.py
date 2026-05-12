# app/parsers/rpi_parser.py
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
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def _is_excluded_iface(name: str) -> bool:
    return any(name.startswith(p) for p in EXCLUDED_IFACE_PREFIXES)


def _is_excluded_ip(ip: str) -> bool:
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
    """Parse output of 'free -m'. Returns total, used, free in MB."""
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
    """Parse output of 'df -h' for root filesystem."""
    result = {}
    for line in clean(text).splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[5] == "/":
            result["total"]      = parts[1]
            result["used"]       = parts[2]
            result["available"]  = parts[3]
            result["used_pct"]   = parts[4].replace("%", "")
            result["filesystem"] = parts[0]
            break
    return result


def parse_temperature(text: str) -> Optional[str]:
    """Parse 'vcgencmd measure_temp' output. Example: temp=47.8'C → '47.8'"""
    text = clean(text)
    m = re.search(r"temp=([0-9.]+)", text)
    return m.group(1) if m else None


# ── Parsers réseau ────────────────────────────────────────────────────────────

def parse_ip_addr(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse output of 'ip a' to find the best LAN interface.
    Priority: eth0 > eth1 > wlan0 > first found.
    Returns: (lan_iface, lan_ip, mac)
    """
    text = clean(text)

    current_iface = None
    current_mac   = None
    candidates    = []

    for line in text.splitlines():
        line = line.strip()

        iface_match = re.match(
            r"^\d+:\s+([^:@\s]+)(?:@[^\s:]+)?:\s+<",
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

        mac_match = re.match(r"link/ether\s+([0-9a-f:]{17})", line, re.IGNORECASE)
        if mac_match:
            current_mac = mac_match.group(1).upper()
            continue

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

    candidates.sort(key=lambda c: IFACE_PRIORITY.get(c[0], 99))
    iface, ip, mac = candidates[0]
    logger.info(
        "[PARSER] ip a: LAN interface selected → %s / %s (mac=%s)",
        iface, ip, mac,
    )
    return iface, ip, mac


def parse_ip_route_dev(text: str) -> Optional[str]:
    """Parse 'ip r s dev <iface>' to extract gateway IP."""
    text = clean(text)
    if not text:
        return None

    for line in text.splitlines():
        m = re.match(r"^default\s+via\s+(\d+\.\d+\.\d+\.\d+)", line.strip())
        if m:
            gw = m.group(1)
            if _is_valid_ip(gw):
                return gw

    for line in text.splitlines():
        m = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", line.strip())
        if m:
            gw = m.group(1)
            if _is_valid_ip(gw):
                return gw

    return None


def detect_hgw(ip_a_text: str, ip_route_text: str) -> dict:
    """Combine parse_ip_addr + parse_ip_route_dev."""
    iface, ip, mac = parse_ip_addr(ip_a_text)
    if not iface:
        return {}
    gw = parse_ip_route_dev(ip_route_text)
    return {"interface": iface, "local_ip": ip, "mac": mac, "gateway": gw}


def parse_ip_neigh_gateway_mac(text: str) -> Optional[str]:
    """
    Parse 'ip neigh show <gw_ip> dev <iface>'.
    Example: 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
    Returns uppercase MAC or None.
    """
    text = clean(text)
    if not text:
        return None
    m = re.search(
        r"\blladdr\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b",
        text,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


# ── Parsers processus ─────────────────────────────────────────────────────────

def parse_ps_scripts(text: str) -> tuple[list[str], list[str]]:
    """Parse 'ps aux' to find running .sh scripts and python processes."""
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

_DOCKER_ERR_PATTERNS = (
    "permission denied",
    "cannot connect to the docker daemon",
    "is the docker daemon running",
    "error during connect",
    "no such file or directory",
    "connection refused",
    "error response from daemon",
)

# Colonnes attendues pour docker ps / docker images
_PS_COLS     = ["CONTAINER ID", "IMAGE", "COMMAND", "CREATED", "STATUS", "PORTS", "NAMES"]
_IMAGES_COLS = ["REPOSITORY", "TAG", "IMAGE ID", "CREATED", "SIZE"]


def _docker_has_error(text: str) -> bool:
    """True si le texte contient une erreur Docker connue."""
    low = text.lower()
    if "command not found" in low or "not found" in low:
        return True
    return any(p in low for p in _DOCKER_ERR_PATTERNS)


def _skip_shell_noise(lines: list[str]) -> list[str]:
    """
    Supprime les lignes parasites qui ne font pas partie de l'output Docker :
      - Échos shell (set -x) : '+ docker ps ...'  '++ docker ...'
      - Ligne qui reproduit exactement la commande envoyée :
            'docker ps -a 2>&1'
            'docker images 2>&1'
    """
    filtered = []
    for line in lines:
        s = line.strip()

        # PS4 / set -x echo : commence par un ou plusieurs '+'
        if re.match(r"^\++\s+", s):
            logger.debug("[PARSER] skipping shell echo (PS4): %r", s[:80])
            continue

        # Ligne qui est la commande elle-même (sans PS4)
        if re.match(
            r"^docker\s+(ps|images)\b",
            s,
            re.IGNORECASE,
        ):
            logger.debug("[PARSER] skipping command echo: %r", s[:80])
            continue

        filtered.append(line)

    return filtered


def _find_column_offsets(header_line: str, col_names: list[str]) -> dict[str, int]:
    """
    Localise chaque colonne dans la ligne header par son offset caractère.

    Exemple :
        "CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES"
        → {"CONTAINER ID": 0, "IMAGE": 15, "COMMAND": 23, ...}
    """
    header_upper = header_line.upper()
    offsets: dict[str, int] = {}
    for col in col_names:
        idx = header_upper.find(col)
        if idx != -1:
            offsets[col] = idx
        else:
            logger.debug("[PARSER] column not found in header: %r", col)
    return offsets


def _split_by_offsets(line: str, col_offsets: dict[str, int]) -> dict[str, str]:
    """
    Découpe une ligne selon les offsets de colonnes calculés depuis le header.
    Gère les lignes plus courtes que le header (ex : PORTS vide en fin de ligne).
    """
    sorted_cols = sorted(col_offsets.items(), key=lambda x: x[1])
    result: dict[str, str] = {}

    for i, (col_name, start) in enumerate(sorted_cols):
        end     = sorted_cols[i + 1][1] if i + 1 < len(sorted_cols) else len(line)
        segment = line[start:end] if start < len(line) else ""
        result[col_name] = segment

    return result


# ── Docker containers ─────────────────────────────────────────────────────────

def parse_docker_ps(text: str) -> tuple[bool, list[dict]]:
    """
    Parse output of 'docker ps -a' (table format).

    Expected header:
        CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES

    Returns:
        (docker_usable, containers_list)

    docker_usable = False si Docker absent / daemon inaccessible.
    """
    text = clean(text)

    if not text:
        # Docker OK, simplement 0 conteneurs
        return True, []

    if _docker_has_error(text):
        logger.warning("[PARSER] docker ps: error detected: %r", text[:200])
        return False, []

    # Filtrer les lignes parasites (échos shell)
    lines = _skip_shell_noise(
        [l for l in text.splitlines() if l.strip()]
    )

    if not lines:
        return True, []

    # ── Trouver le header ──────────────────────────────────────────────────
    header_idx = None
    for i, line in enumerate(lines):
        if "CONTAINER" in line.upper() and "IMAGE" in line.upper():
            header_idx = i
            break

    if header_idx is None:
        logger.warning(
            "[PARSER] docker ps: no valid header found in output:\n%s",
            "\n".join(lines[:5]),
        )
        return True, []

    header      = lines[header_idx]
    col_offsets = _find_column_offsets(header, _PS_COLS)
    logger.debug("[PARSER] docker ps: column offsets: %s", col_offsets)

    containers: list[dict] = []

    for line in lines[header_idx + 1:]:
        line_rstripped = line.rstrip()
        if not line_rstripped.strip():
            continue

        cols = _split_by_offsets(line_rstripped, col_offsets)

        container_id = cols.get("CONTAINER ID", "").strip()
        if not container_id:
            continue

        containers.append({
            "container_id": container_id,
            "image":        cols.get("IMAGE",   "").strip(),
            "command":      cols.get("COMMAND", "").strip().strip('"'),
            "created":      cols.get("CREATED", "").strip(),
            "status":       cols.get("STATUS",  "").strip(),
            "ports":        cols.get("PORTS",   "").strip(),
            "name":         cols.get("NAMES",   "").strip(),
        })

    logger.debug("[PARSER] docker ps: parsed %d containers", len(containers))
    return True, containers


# ── Docker images ─────────────────────────────────────────────────────────────

def parse_docker_images(text: str) -> list[dict]:
    """
    Parse output of 'docker images' (table format).

    Expected header:
        REPOSITORY   TAG   IMAGE ID   CREATED   SIZE

    Gère les REPOSITORY très longs (pas de troncature par défaut).
    """
    text = clean(text)

    if not text:
        return []

    if _docker_has_error(text):
        logger.warning("[PARSER] docker images: error detected: %r", text[:200])
        return []

    # Filtrer les lignes parasites (échos shell)
    lines = _skip_shell_noise(
        [l for l in text.splitlines() if l.strip()]
    )

    if not lines:
        return []

    # ── Trouver le header ──────────────────────────────────────────────────
    header_idx = None
    for i, line in enumerate(lines):
        if "REPOSITORY" in line.upper() and "TAG" in line.upper():
            header_idx = i
            break

    if header_idx is None:
        logger.warning(
            "[PARSER] docker images: no valid header found in output:\n%s",
            "\n".join(lines[:5]),
        )
        return []

    header      = lines[header_idx]
    col_offsets = _find_column_offsets(header, _IMAGES_COLS)
    logger.debug("[PARSER] docker images: column offsets: %s", col_offsets)

    images: list[dict] = []

    for line in lines[header_idx + 1:]:
        line_rstripped = line.rstrip()
        if not line_rstripped.strip():
            continue

        cols = _split_by_offsets(line_rstripped, col_offsets)

        repository = cols.get("REPOSITORY", "").strip()
        if not repository:
            continue

        images.append({
            "repository": repository,
            "tag":        cols.get("TAG",      "").strip(),
            "image_id":   cols.get("IMAGE ID", "").strip(),
            "created":    cols.get("CREATED",  "").strip(),
            "size":       cols.get("SIZE",     "").strip(),
        })

    logger.debug("[PARSER] docker images: parsed %d images", len(images))
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