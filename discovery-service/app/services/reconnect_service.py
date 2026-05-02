# app/services/reconnect_service.py
import time
from typing import Optional, Tuple

import paramiko
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.ssh_manager import SSHSession
from app.infrastructure.telnet_manager import NetgearTelnetSession
from app.infrastructure.netgear_client import NetgearClient
from app.infrastructure.rpi_client import RpiClient
from app.infrastructure.hgw_client import HgwClient
from app.repositories.switch_repo import SwitchRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.hgw_repo import HgwRepository


class ReconnectService:
    def __init__(self, db: Session):
        self.db = db
        self.switch_repo = SwitchRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.hgw_repo = HgwRepository(db)

    def _connect_bastion(self) -> Tuple[SSHSession, paramiko.SSHClient]:
        bastion = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=15,
        )
        ok, msg = bastion.connect()
        if not ok or not bastion._client:
            bastion.close()
            raise ConnectionError(f"Bastion SSH failed: {msg}")
        return bastion, bastion._client

    def _rpi_credentials_chain(self, rpi_ip: str) -> list[tuple[str, str]]:
        chain: list[tuple[str, str]] = []

        rpi_db = self.rpi_repo.get_by_ip(rpi_ip)
        if rpi_db and rpi_db.custom_ssh_user and rpi_db.custom_ssh_pass:
            chain.append((rpi_db.custom_ssh_user, rpi_db.custom_ssh_pass))

        default_creds = (settings.RPI_SSH_USER, settings.RPI_SSH_PASS)
        fallback_creds = (settings.RPI_SSH_FALLBACK_USER, settings.RPI_SSH_FALLBACK_PASS)

        if default_creds not in chain:
            chain.append(default_creds)
        if fallback_creds not in chain:
            chain.append(fallback_creds)

        return chain

    # ─────────────────────────────────────────────────────────────
    # SWITCH (TELNET via bastion)
    # ─────────────────────────────────────────────────────────────
    def reconnect_switch(self, switch_id: int) -> dict:
        sw = self.switch_repo.get_by_id(switch_id)
        if not sw:
            raise ValueError("Switch not found")

        started = time.perf_counter()
        bastion_session = None
        telnet_session = None

        try:
            bastion_session, bastion_client = self._connect_bastion()

            telnet_session = NetgearTelnetSession(
                switch_ip=sw.ip,
                switch_port=sw.telnet_port,
                username=sw.telnet_user,
                password=sw.telnet_pass,
                bastion_client=bastion_client,
                timeout=20,
            )

            ok, msg = telnet_session.connect()
            if not ok:
                elapsed = time.perf_counter() - started
                return {"success": False, "target": sw.ip, "elapsed_s": round(elapsed, 3), "message": msg}

            data = NetgearClient(telnet_session).collect_all()
            if not data.success:
                elapsed = time.perf_counter() - started
                return {"success": False, "target": sw.ip, "elapsed_s": round(elapsed, 3), "message": data.error or "collect failed"}

            # update Switch "current state"
            sw.last_seen = __import__("datetime").datetime.utcnow()
            sw.mac_address = data.info.mac_address
            sw.firmware_version = data.info.firmware_version
            sw.uptime = data.info.uptime
            sw.serial_number = data.info.serial_number
            sw.model = data.info.model
            self.db.commit()

            elapsed = time.perf_counter() - started
            return {
                "success": True,
                "target": sw.ip,
                "elapsed_s": round(elapsed, 3),
                "message": "Switch reconnected and collected successfully",
                "details": {
                    "model": data.info.model,
                    "firmware_version": data.info.firmware_version,
                    "mac_count": len(data.mac_entries),
                },
            }

        finally:
            if telnet_session:
                telnet_session.close()
            if bastion_session:
                bastion_session.close()

    # ─────────────────────────────────────────────────────────────
    # RPI (SSH via bastion)
    # ─────────────────────────────────────────────────────────────
    def reconnect_rpi(self, ip_mgmt: str) -> dict:
        rpi = self.rpi_repo.get_by_ip(ip_mgmt)
        if not rpi:
            raise ValueError("RPi not found")

        started = time.perf_counter()
        bastion_session = None
        rpi_session = None

        try:
            bastion_session, bastion_client = self._connect_bastion()

            last_err = "unknown"
            used_user: Optional[str] = None

            for u, p in self._rpi_credentials_chain(ip_mgmt):
                rpi_session = SSHSession(
                    host=ip_mgmt,
                    username=u,
                    password=p,
                    port=22,
                    tunnel=bastion_client,
                    timeout=15,
                )
                ok, msg = rpi_session.connect()
                if ok:
                    used_user = u
                    collected = RpiClient(rpi_session).collect_all(ip_mgmt)

                    # update RPi "current state"
                    self.rpi_repo.update_ssh_status(
                        ip_mgmt=ip_mgmt,
                        success=True,
                        error=None,
                        hgw_ip=collected.hgw_ip,
                    )

                    elapsed = time.perf_counter() - started
                    return {
                        "success": True,
                        "target": ip_mgmt,
                        "elapsed_s": round(elapsed, 3),
                        "message": f"RPi reconnected successfully (user={used_user})",
                        "details": {
                            "used_user": used_user,
                            "hostname": collected.hostname,
                            "lan_ip": collected.lan_ip,
                            "hgw_ip": collected.hgw_ip,
                            "temp_celsius": collected.temp_celsius,
                        },
                    }

                last_err = msg
                if rpi_session:
                    rpi_session.close()
                    rpi_session = None

            # all failed
            self.rpi_repo.update_ssh_status(ip_mgmt=ip_mgmt, success=False, error=last_err)
            elapsed = time.perf_counter() - started
            return {"success": False, "target": ip_mgmt, "elapsed_s": round(elapsed, 3), "message": last_err}

        finally:
            if rpi_session:
                rpi_session.close()
            if bastion_session:
                bastion_session.close()

    # ─────────────────────────────────────────────────────────────
    # HGW (SSH via RPi tunnel)
    # ─────────────────────────────────────────────────────────────
    def reconnect_hgw(self, hgw_ip: str, via_rpi_ip: Optional[str]) -> dict:
        if not via_rpi_ip:
            # try from DB
            hgw_db = self.hgw_repo.get_by_ip(hgw_ip)
            via_rpi_ip = hgw_db.via_rpi_ip if hgw_db else None

        if not via_rpi_ip:
            raise ValueError("via_rpi_ip is required (no known RPi to use as tunnel)")

        started = time.perf_counter()
        bastion_session = None
        rpi_session = None
        hgw_session = None

        try:
            bastion_session, bastion_client = self._connect_bastion()

            # connect to via_rpi_ip first
            last_err = "cannot connect to via_rpi"
            for u, p in self._rpi_credentials_chain(via_rpi_ip):
                rpi_session = SSHSession(
                    host=via_rpi_ip,
                    username=u,
                    password=p,
                    port=22,
                    tunnel=bastion_client,
                    timeout=15,
                )
                ok, msg = rpi_session.connect()
                if ok:
                    break
                last_err = msg
                rpi_session.close()
                rpi_session = None

            if not rpi_session or not rpi_session._client:
                elapsed = time.perf_counter() - started
                return {
                    "success": False,
                    "target": hgw_ip,
                    "via": via_rpi_ip,
                    "elapsed_s": round(elapsed, 3),
                    "message": f"Cannot SSH to via_rpi_ip: {last_err}",
                }

            # connect to HGW through tunnel=rpi_session._client
            hgw_session = SSHSession(
                host=hgw_ip,
                username=settings.HGW_SSH_USER,
                password=settings.HGW_SSH_PASS,
                port=22,
                tunnel=rpi_session._client,
                timeout=20,
            )
            ok_h, msg_h = hgw_session.connect()
            if not ok_h:
                elapsed = time.perf_counter() - started
                return {
                    "success": False,
                    "target": hgw_ip,
                    "via": via_rpi_ip,
                    "elapsed_s": round(elapsed, 3),
                    "message": msg_h,
                }

            info = HgwClient(hgw_session).collect_deviceinfo(hgw_ip, via_rpi_ip)

            # ensure exists + update current state on success
            self.hgw_repo.upsert(hgw_ip, via_rpi_ip=via_rpi_ip)
            if info.success:
                self.hgw_repo.update_from_fact(hgw_ip, info)

            elapsed = time.perf_counter() - started
            return {
                "success": bool(info.success),
                "target": hgw_ip,
                "via": via_rpi_ip,
                "elapsed_s": round(elapsed, 3),
                "message": "HGW reconnected and collected" if info.success else (info.error or "HGW collect failed"),
                "details": {
                    "manufacturer": info.manufacturer,
                    "model_name": info.model_name,
                    "software_version": info.software_version,
                    "serial_number": info.serial_number,
                    "external_ip": info.external_ip,
                },
            }

        finally:
            if hgw_session:
                hgw_session.close()
            if rpi_session:
                rpi_session.close()
            if bastion_session:
                bastion_session.close()