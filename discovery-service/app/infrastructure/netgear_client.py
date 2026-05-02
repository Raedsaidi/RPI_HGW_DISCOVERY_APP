import logging
from typing import Optional
from dataclasses import dataclass

from app.infrastructure.telnet_manager import NetgearTelnetSession
from app.parsers.netgear_parser import (
    parse_show_info,
    parse_show_ip,
    parse_mac_table,
    parse_cpu_status,
    SwitchInfo,
    MacEntry,
    CpuStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class SwitchCollectedData:
    info: SwitchInfo
    ip_info: dict
    cpu: CpuStatus
    mac_entries: list[MacEntry]
    raw_show_info: str
    raw_show_cpu: str
    raw_show_mac: str
    success: bool = True
    error: Optional[str] = None


class NetgearClient:
    """
    High-level client for collecting data from a Netgear switch
    using a persistent Telnet session.
    """

    def __init__(self, session: NetgearTelnetSession):
        self.session = session

    def collect_all(self) -> SwitchCollectedData:
        """Collect all relevant data from the switch."""
        logger.info("[NETGEAR] Starting collection for switch %s", self.session.switch_ip)

        # 1. show info
        ok_info, raw_info = self.session.execute("show info")
        if not ok_info:
            return SwitchCollectedData(
                info=SwitchInfo(),
                ip_info={},
                cpu=CpuStatus(),
                mac_entries=[],
                raw_show_info="",
                raw_show_cpu="",
                raw_show_mac="",
                success=False,
                error=f"show info failed: {raw_info}",
            )

        # 2. show ip
        ok_ip, raw_ip = self.session.execute("show ip")

        # 3. show cpu status
        ok_cpu, raw_cpu = self.session.execute("show cpu status")

        # 4. show mac address-table
        ok_mac, raw_mac = self.session.execute("show mac address-table")

        info = parse_show_info(raw_info)
        ip_info = parse_show_ip(raw_ip) if ok_ip else {}
        cpu = parse_cpu_status(raw_cpu) if ok_cpu else CpuStatus()
        mac_entries = parse_mac_table(raw_mac) if ok_mac else []

        # Merge gateway from show ip if available
        if ip_info.get("default_gateway") and not info.default_gateway:
            info.default_gateway = ip_info.get("default_gateway")

        logger.info(
            "[NETGEAR] Collected switch %s: %d MAC entries, firmware=%s",
            self.session.switch_ip,
            len(mac_entries),
            info.firmware_version,
        )

        return SwitchCollectedData(
            info=info,
            ip_info=ip_info,
            cpu=cpu,
            mac_entries=mac_entries,
            raw_show_info=raw_info,
            raw_show_cpu=raw_cpu if ok_cpu else "",
            raw_show_mac=raw_mac if ok_mac else "",
            success=True,
        )