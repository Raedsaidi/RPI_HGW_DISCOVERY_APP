import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.infrastructure.ssh_manager import SSHSession

logger = logging.getLogger(__name__)


def _norm_mac(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().replace("-", ":").upper()
    if re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", v):
        return v
    return value.strip().upper()


@dataclass
class HgwCollectedData:
    hgw_ip: str
    via_rpi_ip: str

    # RPi docker client container id/name when HGW is only reachable from that namespace
    via_docker_container_id: Optional[str] = None

    # NEW: clé d’instance (set par DiscoveryService)
    instance_key: Optional[str] = None

    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    serial_number: Optional[str] = None
    software_version: Optional[str] = None
    hardware_version: Optional[str] = None
    external_ip: Optional[str] = None
    uptime_seconds: Optional[int] = None
    mem_free_kb: Optional[int] = None
    mem_total_kb: Optional[int] = None
    base_mac: Optional[str] = None
    country: Optional[str] = None
    device_status: Optional[str] = None

    raw_deviceinfo: str = ""
    success: bool = True
    error: Optional[str] = None


class HgwClient:
    def __init__(self, session: SSHSession):
        self.session = session

    def collect_deviceinfo(self, hgw_ip: str, via_rpi_ip: str) -> HgwCollectedData:
        logger.info("[HGW] Collecting DeviceInfo from %s (via RPi %s)", hgw_ip, via_rpi_ip)

        ok, raw = self.session.execute(
            'ba-cli -a -j -- "DeviceInfo.?"',
            timeout=40,
            idle_timeout=5.0,
        )

        if not ok:
            ok, raw = self.session.execute(
                'echo "DeviceInfo.?" | ba-cli -a -j',
                timeout=40,
                idle_timeout=5.0,
            )

        if not ok:
            logger.warning("[HGW] Failed to collect from %s: %s", hgw_ip, raw)
            return HgwCollectedData(
                hgw_ip=hgw_ip,
                via_rpi_ip=via_rpi_ip,
                raw_deviceinfo=raw,
                success=False,
                error=raw,
            )

        parsed = self._parse_deviceinfo(raw)
        parsed.hgw_ip = hgw_ip
        parsed.via_rpi_ip = via_rpi_ip
        parsed.raw_deviceinfo = raw
        parsed.success = True

        logger.info(
            "[HGW] Collected %s: model=%s, fw=%s, uptime=%s, serial=%s",
            hgw_ip,
            parsed.model_name,
            parsed.software_version,
            parsed.uptime_seconds,
            parsed.serial_number,
        )

        return parsed

    def _extract_json_array(self, text: str) -> Optional[str]:
        if not text:
            return None
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start:end + 1]

    def _parse_deviceinfo(self, text: str) -> HgwCollectedData:
        data = HgwCollectedData(hgw_ip="", via_rpi_ip="")

        json_str = self._extract_json_array(text)
        if json_str:
            try:
                json_data = json.loads(json_str)
                if isinstance(json_data, list) and json_data:
                    obj = json_data[0]

                    di = obj.get("DeviceInfo.")
                    if not isinstance(di, dict):
                        di = obj.get("DeviceInfo", {})
                    if not isinstance(di, dict):
                        di = {}

                    ms = obj.get("DeviceInfo.MemoryStatus.")
                    if not isinstance(ms, dict):
                        ms = obj.get("DeviceInfo.MemoryStatus", {})
                    if not isinstance(ms, dict):
                        ms = {}

                    data.manufacturer = di.get("Manufacturer")
                    data.model_name = di.get("ModelName")
                    data.serial_number = di.get("SerialNumber")
                    data.software_version = di.get("SoftwareVersion")
                    data.hardware_version = di.get("HardwareVersion")
                    data.external_ip = di.get("ExternalIPAddress")

                    base_mac = di.get("BaseMAC") or di.get("BaseMACAddress")
                    data.base_mac = _norm_mac(base_mac)

                    data.country = di.get("Country")
                    data.device_status = di.get("DeviceStatus")

                    uptime = di.get("UpTime")
                    if uptime is not None:
                        try:
                            data.uptime_seconds = int(uptime)
                        except Exception:
                            pass

                    free = ms.get("Free")
                    if free is not None:
                        try:
                            data.mem_free_kb = int(free)
                        except Exception:
                            pass

                    total = ms.get("Total")
                    if total is not None:
                        try:
                            data.mem_total_kb = int(total)
                        except Exception:
                            pass

                    return data
            except json.JSONDecodeError:
                pass

        # Fallback key=value
        for line in (text or "").splitlines():
            line = line.strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"')

            if key == "DeviceInfo.Manufacturer":
                data.manufacturer = val
            elif key == "DeviceInfo.ModelName":
                data.model_name = val
            elif key == "DeviceInfo.SerialNumber":
                data.serial_number = val
            elif key == "DeviceInfo.SoftwareVersion":
                data.software_version = val
            elif key == "DeviceInfo.HardwareVersion":
                data.hardware_version = val
            elif key == "DeviceInfo.ExternalIPAddress":
                data.external_ip = val
            elif key == "DeviceInfo.UpTime":
                try:
                    data.uptime_seconds = int(val)
                except Exception:
                    pass
            elif key in ("DeviceInfo.BaseMAC", "DeviceInfo.BaseMACAddress"):
                data.base_mac = _norm_mac(val)
            elif key == "DeviceInfo.Country":
                data.country = val
            elif key == "DeviceInfo.DeviceStatus":
                data.device_status = val
            elif key == "DeviceInfo.MemoryStatus.Free":
                try:
                    data.mem_free_kb = int(val)
                except Exception:
                    pass
            elif key == "DeviceInfo.MemoryStatus.Total":
                try:
                    data.mem_total_kb = int(val)
                except Exception:
                    pass

        return data