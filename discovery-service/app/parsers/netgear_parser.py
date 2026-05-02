import re
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Remove ANSI escape sequences
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def clean_output(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\r", "")
    return text.strip()


@dataclass
class SwitchInfo:
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    default_gateway: Optional[str] = None
    firmware_version: Optional[str] = None
    loader_version: Optional[str] = None
    uptime: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    system_name: Optional[str] = None


@dataclass
class MacEntry:
    vid: Optional[int]
    mac: str
    entry_type: str
    port: str
    raw_line: str


@dataclass
class CpuStatus:
    cpu_5s: Optional[str] = None
    cpu_60s: Optional[str] = None
    cpu_300s: Optional[str] = None
    mem_free_kb: Optional[int] = None
    mem_alloc_kb: Optional[int] = None


def parse_show_info(text: str) -> SwitchInfo:
    """Parse output of 'show info' command."""
    info = SwitchInfo()
    text = clean_output(text)

    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if key == "MAC Address":
            info.mac_address = val
        elif key == "IP Address":
            info.ip_address = val
        elif key == "Subnet Mask":
            info.subnet_mask = val
        elif key == "Firmware Version":
            info.firmware_version = val
        elif key == "Loader Version":
            info.loader_version = val
        elif key == "System Up Time":
            info.uptime = val
        elif key == "SN":
            info.serial_number = val
        elif key == "System Name":
            info.system_name = val

    # Extract model from output header like "GS728TPv2#"
    model_match = re.search(r"^(GS\d+\S+)[>#]", text, re.MULTILINE)
    if model_match:
        info.model = model_match.group(1)

    return info


def parse_show_ip(text: str) -> dict:
    """Parse output of 'show ip' command."""
    result = {}
    text = clean_output(text)
    in_status = False

    for line in text.splitlines():
        stripped = line.strip()
        if "Status" in stripped:
            in_status = True
            continue
        if not in_status:
            continue
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        if key == "Default Gateway":
            result["default_gateway"] = val
        elif key == "IP Address":
            result["ip_address"] = val

    return result


def parse_mac_table(text: str) -> list[MacEntry]:
    """
    Parse output of 'show mac address-table'.

    Format:
     VID  | MAC Address       | Type    | Ports
    ------+-------------------+---------+----------------
        1 | B8:27:EB:21:CB:AD | Dynamic | g7
    """
    entries: list[MacEntry] = []
    text = clean_output(text)

    for line in text.splitlines():
        # Skip header and separator lines
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        vid_s, mac_s, type_s, port_s = parts[0], parts[1], parts[2], parts[3]

        # Skip header row
        if "MAC Address" in mac_s or "VID" in vid_s:
            continue

        # Must contain a MAC address
        if not re.match(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac_s):
            continue

        try:
            vid = int(vid_s) if vid_s.isdigit() else None
        except ValueError:
            vid = None

        entries.append(MacEntry(
            vid=vid,
            mac=mac_s.upper(),
            entry_type=type_s,
            port=port_s,
            raw_line=line,
        ))

    logger.debug("[NETGEAR] Parsed %d MAC entries.", len(entries))
    return entries


def parse_cpu_status(text: str) -> CpuStatus:
    """Parse output of 'show cpu status'."""
    status = CpuStatus()
    text = clean_output(text)

    # Memory
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("free"):
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    status.mem_free_kb = int(parts[1])
                except ValueError:
                    pass
        elif stripped.startswith("alloc"):
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    status.mem_alloc_kb = int(parts[1])
                except ValueError:
                    pass

    # Total CPU line
    total_match = re.search(
        r"Total CPU Utilization\s+(\S+)\s+(\S+)\s+(\S+)",
        text, re.IGNORECASE
    )
    if total_match:
        status.cpu_5s = total_match.group(1)
        status.cpu_60s = total_match.group(2)
        status.cpu_300s = total_match.group(3)

    return status