import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Match active dhcp-host lines only (not commented)
RE_DHCP_HOST = re.compile(
    r"^\s*dhcp-host=(?P<mac>([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})"
    r"[^,]*,set:piserver,(?P<ip>\d+\.\d+\.\d+\.\d+)\s*$"
)

# Match group comments like ##Rob or ##48H_Rob
RE_GROUP_COMMENT = re.compile(r"^\s*##(.+)$")

# Match inline comments like #8gb_rpi
RE_INLINE_COMMENT = re.compile(r"^\s*#(?!#)(?!dhcp-host)(.+)$")


@dataclass
class RpiEntry:
    mac: str
    ip_mgmt: str
    label: Optional[str] = None
    group: Optional[str] = None


def parse_piserver(text: str) -> list[RpiEntry]:
    """
    Parse /etc/dnsmasq.d/piserver content.

    Rules:
    - Lines starting with '#dhcp-host=' are COMMENTED OUT → IGNORED
    - Lines starting with '##' are group labels
    - Lines starting with '#' (single) before a dhcp-host are inline labels
    - Active lines: dhcp-host=MAC,set:piserver,IP
    """
    out: list[RpiEntry] = []
    current_group: Optional[str] = None
    last_inline_label: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()

        # Skip commented-out dhcp-host lines
        if stripped.startswith("#dhcp-host="):
            last_inline_label = None
            continue

        # Group comment ##...
        gm = RE_GROUP_COMMENT.match(stripped)
        if gm:
            current_group = gm.group(1).strip()
            last_inline_label = None
            continue

        # Inline label #...
        im = RE_INLINE_COMMENT.match(stripped)
        if im:
            last_inline_label = im.group(1).strip()
            continue

        # Active dhcp-host line
        m = RE_DHCP_HOST.match(line)
        if m:
            mac = m.group("mac").upper()
            ip = m.group("ip")
            label = last_inline_label or current_group
            out.append(RpiEntry(mac=mac, ip_mgmt=ip, label=label, group=current_group))
            last_inline_label = None
            continue

        # Reset inline label on other lines
        last_inline_label = None

    logger.info("[PISERVER] Parsed %d active RPi entries.", len(out))
    return out