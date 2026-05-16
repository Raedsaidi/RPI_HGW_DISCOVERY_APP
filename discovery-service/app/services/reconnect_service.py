# app/services/reconnect_service.py
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional, Tuple
from uuid import uuid4

import paramiko
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.hgw_client import HgwClient
from app.infrastructure.netgear_client import NetgearClient
from app.infrastructure.rpi_client import RpiClient
from app.infrastructure.ssh_manager import SSHSession
from app.infrastructure.telnet_manager import HgwTelnetSession, NetgearTelnetSession
from app.repositories.hgw_repo import HgwRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.switch_repo import SwitchRepository

logger = logging.getLogger(__name__)


class ReconnectService:
    def __init__(self, db: Session):
        self.db = db
        self.switch_repo = SwitchRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.hgw_repo = HgwRepository(db)

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _elapsed_s(started: float) -> float:
        return round(time.perf_counter() - started, 3)

    def _safe_commit(self, *, ctx: str, op_id: str) -> None:
        try:
            self.db.commit()
        except Exception:
            logger.exception("[op=%s] DB commit failed (%s) -> rollback", op_id, ctx)
            self.db.rollback()
            raise

    @staticmethod
    def _safe_close(name: str, obj, *, op_id: str) -> None:
        if not obj:
            return
        try:
            obj.close()
        except Exception:
            logger.exception("[op=%s] Failed to close %s", op_id, name)

    def _connect_bastion(self, *, op_id: str) -> Tuple[SSHSession, paramiko.SSHClient]:
        logger.info(
            "[op=%s] Connecting to bastion host=%s user=%s port=22",
            op_id,
            settings.PISERVER_HOST,
            settings.PISERVER_USER,
        )

        started = time.perf_counter()
        bastion = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,  # do not log
            port=22,
            tunnel=None,
            timeout=60,
        )

        ok, msg = bastion.connect()
        logger.info(
            "[op=%s] Bastion connect result ok=%s elapsed_s=%.3f msg=%s",
            op_id,
            ok,
            self._elapsed_s(started),
            msg,
        )

        if not ok or not bastion._client:
            self._safe_close("bastion_session", bastion, op_id=op_id)
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
        op_id = uuid4().hex[:10]
        started = time.perf_counter()

        logger.info("[op=%s] SWITCH reconnect start switch_id=%s", op_id, switch_id)

        sw = self.switch_repo.get_by_id(switch_id)
        if not sw:
            logger.warning("[op=%s] SWITCH not found switch_id=%s", op_id, switch_id)
            raise ValueError("Switch not found")

        bastion_session = None
        telnet_session = None

        try:
            bastion_session, bastion_client = self._connect_bastion(op_id=op_id)

            logger.info(
                "[op=%s] SWITCH telnet connect start target=%s port=%s user=%s",
                op_id,
                sw.ip,
                sw.telnet_port,
                sw.telnet_user,
            )
            t0 = time.perf_counter()
            telnet_session = NetgearTelnetSession(
                switch_ip=sw.ip,
                switch_port=sw.telnet_port,
                username=sw.telnet_user,
                password=sw.telnet_pass,  # do not log
                bastion_client=bastion_client,
                timeout=60,
            )
            ok, msg = telnet_session.connect()
            logger.info(
                "[op=%s] SWITCH telnet connect result ok=%s elapsed_s=%.3f msg=%s",
                op_id,
                ok,
                self._elapsed_s(t0),
                msg,
            )
            if not ok:
                return {
                    "success": False,
                    "target": sw.ip,
                    "elapsed_s": self._elapsed_s(started),
                    "message": msg,
                }

            logger.info("[op=%s] SWITCH collect start target=%s", op_id, sw.ip)
            t1 = time.perf_counter()
            data = NetgearClient(telnet_session).collect_all()
            logger.info(
                "[op=%s] SWITCH collect result success=%s elapsed_s=%.3f error=%s",
                op_id,
                bool(data.success),
                self._elapsed_s(t1),
                data.error,
            )
            if not data.success:
                return {
                    "success": False,
                    "target": sw.ip,
                    "elapsed_s": self._elapsed_s(started),
                    "message": data.error or "collect failed",
                }

            # update Switch "current state"
            sw.last_seen = datetime.utcnow()
            sw.mac_address = data.info.mac_address
            sw.firmware_version = data.info.firmware_version
            sw.uptime = data.info.uptime
            sw.serial_number = data.info.serial_number
            sw.model = data.info.model

            self._safe_commit(ctx="reconnect_switch", op_id=op_id)

            logger.info(
                "[op=%s] SWITCH reconnect success target=%s elapsed_s=%.3f model=%s firmware=%s",
                op_id,
                sw.ip,
                self._elapsed_s(started),
                data.info.model,
                data.info.firmware_version,
            )

            return {
                "success": True,
                "target": sw.ip,
                "elapsed_s": self._elapsed_s(started),
                "message": "Switch reconnected and collected successfully",
                "details": {
                    "model": data.info.model,
                    "firmware_version": data.info.firmware_version,
                    "mac_count": len(data.mac_entries),
                },
            }

        except Exception as e:
            logger.exception(
                "[op=%s] SWITCH reconnect crashed switch_id=%s target=%s elapsed_s=%.3f err=%s",
                op_id,
                switch_id,
                getattr(sw, "ip", None),
                self._elapsed_s(started),
                e,
            )
            # important if caller continues using same Session
            self.db.rollback()
            raise

        finally:
            self._safe_close("switch_telnet_session", telnet_session, op_id=op_id)
            self._safe_close("bastion_session", bastion_session, op_id=op_id)

    # ─────────────────────────────────────────────────────────────
    # RPI (SSH via bastion)
    # ─────────────────────────────────────────────────────────────
    def reconnect_rpi(self, ip_mgmt: str) -> dict:
        op_id = uuid4().hex[:10]
        started = time.perf_counter()

        logger.info("[op=%s] RPI reconnect start ip_mgmt=%s", op_id, ip_mgmt)

        rpi = self.rpi_repo.get_by_ip(ip_mgmt)
        if not rpi:
            logger.warning("[op=%s] RPI not found ip_mgmt=%s", op_id, ip_mgmt)
            raise ValueError("RPi not found")

        bastion_session = None
        rpi_session = None

        try:
            bastion_session, bastion_client = self._connect_bastion(op_id=op_id)

            last_err = "unknown"
            used_user: Optional[str] = None

            chain = self._rpi_credentials_chain(ip_mgmt)
            logger.info("[op=%s] RPI credential chain size=%d target=%s", op_id, len(chain), ip_mgmt)

            for idx, (u, p) in enumerate(chain, start=1):
                logger.info(
                    "[op=%s] RPI ssh attempt=%d/%d target=%s user=%s",
                    op_id,
                    idx,
                    len(chain),
                    ip_mgmt,
                    u,
                )
                t0 = time.perf_counter()
                rpi_session = SSHSession(
                    host=ip_mgmt,
                    username=u,
                    password=p,  # do not log
                    port=22,
                    tunnel=bastion_client,
                    timeout=60,
                )
                ok, msg = rpi_session.connect()
                logger.info(
                    "[op=%s] RPI ssh result ok=%s elapsed_s=%.3f msg=%s",
                    op_id,
                    ok,
                    self._elapsed_s(t0),
                    msg,
                )

                if ok:
                    used_user = u
                    logger.info("[op=%s] RPI collect start target=%s", op_id, ip_mgmt)
                    t1 = time.perf_counter()
                    collected = RpiClient(rpi_session).collect_all(ip_mgmt)
                    logger.info(
                        "[op=%s] RPI collect done elapsed_s=%.3f hostname=%s lan_ip=%s hgw_ip=%s temp=%s",
                        op_id,
                        self._elapsed_s(t1),
                        collected.hostname,
                        collected.lan_ip,
                        collected.hgw_ip,
                        collected.temp_celsius,
                    )

                    # update RPi "current state"
                    self.rpi_repo.update_ssh_status(
                        ip_mgmt=ip_mgmt,
                        success=True,
                        error=None,
                        hgw_ip=collected.hgw_ip,
                    )

                    logger.info(
                        "[op=%s] RPI reconnect success target=%s elapsed_s=%.3f user=%s",
                        op_id,
                        ip_mgmt,
                        self._elapsed_s(started),
                        used_user,
                    )

                    return {
                        "success": True,
                        "target": ip_mgmt,
                        "elapsed_s": self._elapsed_s(started),
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
                self._safe_close("rpi_session", rpi_session, op_id=op_id)
                rpi_session = None

            # all failed
            logger.warning(
                "[op=%s] RPI reconnect failed target=%s elapsed_s=%.3f last_err=%s",
                op_id,
                ip_mgmt,
                self._elapsed_s(started),
                last_err,
            )
            self.rpi_repo.update_ssh_status(ip_mgmt=ip_mgmt, success=False, error=last_err)

            return {
                "success": False,
                "target": ip_mgmt,
                "elapsed_s": self._elapsed_s(started),
                "message": last_err,
            }

        except Exception as e:
            logger.exception(
                "[op=%s] RPI reconnect crashed target=%s elapsed_s=%.3f err=%s",
                op_id,
                ip_mgmt,
                self._elapsed_s(started),
                e,
            )
            self.db.rollback()
            raise

        finally:
            self._safe_close("rpi_session", rpi_session, op_id=op_id)
            self._safe_close("bastion_session", bastion_session, op_id=op_id)

    # ─────────────────────────────────────────────────────────────
    # HGW (SSH via RPi tunnel)
    # ─────────────────────────────────────────────────────────────
    def reconnect_hgw(self, hgw_identifier: str, via_rpi_ip: Optional[str]) -> dict:
        op_id = uuid4().hex[:10]
        started = time.perf_counter()

        logger.info(
            "[op=%s] HGW reconnect start identifier=%s via_rpi_ip=%s",
            op_id,
            hgw_identifier,
            via_rpi_ip,
        )

        # Resolve identifier -> IP + default via_rpi_ip from DB if needed
        hgw_record = self.hgw_repo.get_by_identifier(hgw_identifier)
        hgw_ip = hgw_identifier
        if hgw_record:
            hgw_ip = hgw_record.ip
            if not via_rpi_ip:
                via_rpi_ip = hgw_record.via_rpi_ip

        logger.info(
            "[op=%s] HGW resolved target hgw_ip=%s via_rpi_ip=%s (from_db=%s)",
            op_id,
            hgw_ip,
            via_rpi_ip,
            bool(hgw_record),
        )

        if not via_rpi_ip:
            logger.warning("[op=%s] HGW reconnect abort: via_rpi_ip missing", op_id)
            raise ValueError("via_rpi_ip is required (no known RPi to use as tunnel)")

        dock = None
        if hgw_record:
            dock = (getattr(hgw_record, "via_docker_container_id", None) or "").strip() or None

        bastion_session = None
        rpi_session = None
        hgw_session = None
        telnet_session = None

        try:
            # 1) Bastion
            bastion_session, bastion_client = self._connect_bastion(op_id=op_id)

            # 2) Connect to RPi (via bastion) using credential chain
            last_err = "cannot connect to via_rpi"
            chain = self._rpi_credentials_chain(via_rpi_ip)
            logger.info(
                "[op=%s] HGW connect step=RPi chain_size=%d via_rpi_ip=%s",
                op_id,
                len(chain),
                via_rpi_ip,
            )

            for idx, (u, p) in enumerate(chain, start=1):
                logger.info(
                    "[op=%s] HGW connect step=RPi attempt=%d/%d host=%s user=%s",
                    op_id,
                    idx,
                    len(chain),
                    via_rpi_ip,
                    u,
                )
                t0 = time.perf_counter()
                rpi_session = SSHSession(
                    host=via_rpi_ip,
                    username=u,
                    password=p,  # do not log
                    port=22,
                    tunnel=bastion_client,
                    timeout=60,
                )
                ok, msg = rpi_session.connect()
                logger.info(
                    "[op=%s] HGW connect step=RPi result ok=%s elapsed_s=%.3f msg=%s",
                    op_id,
                    ok,
                    self._elapsed_s(t0),
                    msg,
                )
                if ok:
                    break

                last_err = msg
                self._safe_close("rpi_session", rpi_session, op_id=op_id)
                rpi_session = None

            if not rpi_session or not rpi_session._client:
                logger.warning(
                    "[op=%s] HGW reconnect failed: cannot SSH to via_rpi_ip=%s last_err=%s elapsed_s=%.3f",
                    op_id,
                    via_rpi_ip,
                    last_err,
                    self._elapsed_s(started),
                )
                return {
                    "success": False,
                    "target": hgw_ip,
                    "via": via_rpi_ip,
                    "elapsed_s": self._elapsed_s(started),
                    "message": f"Cannot SSH to via_rpi_ip: {last_err}",
                }

            # 3) Connect to HGW through tunnel=rpi_session._client
            logger.info(
                "[op=%s] HGW connect step=HGW ssh start target=%s via=%s user=%s",
                op_id,
                hgw_ip,
                via_rpi_ip,
                settings.HGW_SSH_USER,
            )
            t1 = time.perf_counter()
            hgw_session = SSHSession(
                host=hgw_ip,
                username=settings.HGW_SSH_USER,
                password=settings.HGW_SSH_PASS,  # do not log
                port=22,
                tunnel=rpi_session._client,
                tunnel_via_docker_container=dock,
                timeout=60,
            )
            ok_h, msg_h = hgw_session.connect()
            logger.info(
                "[op=%s] HGW connect step=HGW ssh result ok=%s elapsed_s=%.3f msg=%s",
                op_id,
                ok_h,
                self._elapsed_s(t1),
                msg_h,
            )

            # 4) Collect deviceinfo (SSH or Telnet fallback)
            if not ok_h:
                logger.warning(
                    "[op=%s] HGW SSH failed target=%s via=%s msg=%s -> trying Telnet fallback",
                    op_id,
                    hgw_ip,
                    via_rpi_ip,
                    msg_h,
                )
                t2 = time.perf_counter()
                telnet_session = HgwTelnetSession(
                    hgw_ip=hgw_ip,
                    hgw_port=settings.HGW_TELNET_PORT,
                    username=settings.HGW_SSH_USER,
                    password=settings.HGW_SSH_PASS,  # do not log
                    tunnel_client=rpi_session._client,
                    timeout=60,
                    tunnel_via_docker_container=dock,
                )
                ok_t, msg_t = telnet_session.connect()
                logger.info(
                    "[op=%s] HGW connect step=HGW telnet result ok=%s elapsed_s=%.3f msg=%s",
                    op_id,
                    ok_t,
                    self._elapsed_s(t2),
                    msg_t,
                )
                if not ok_t:
                    logger.warning(
                        "[op=%s] HGW reconnect failed: SSH+Telnet failed target=%s via=%s elapsed_s=%.3f",
                        op_id,
                        hgw_ip,
                        via_rpi_ip,
                        self._elapsed_s(started),
                    )
                    return {
                        "success": False,
                        "target": hgw_ip,
                        "via": via_rpi_ip,
                        "elapsed_s": self._elapsed_s(started),
                        "message": f"SSH failed: {msg_h}; Telnet failed: {msg_t}",
                    }

                logger.info("[op=%s] HGW collect start (telnet) target=%s", op_id, hgw_ip)
                t3 = time.perf_counter()
                info = HgwClient(telnet_session).collect_deviceinfo(hgw_ip, via_rpi_ip)
                if hgw_record:
                    info.via_docker_container_id = hgw_record.via_docker_container_id
                logger.info(
                    "[op=%s] HGW collect done (telnet) success=%s elapsed_s=%.3f error=%s",
                    op_id,
                    bool(info.success),
                    self._elapsed_s(t3),
                    getattr(info, "error", None),
                )
            else:
                logger.info("[op=%s] HGW collect start (ssh) target=%s", op_id, hgw_ip)
                t3 = time.perf_counter()
                info = HgwClient(hgw_session).collect_deviceinfo(hgw_ip, via_rpi_ip)
                if hgw_record:
                    info.via_docker_container_id = hgw_record.via_docker_container_id
                logger.info(
                    "[op=%s] HGW collect done (ssh) success=%s elapsed_s=%.3f error=%s",
                    op_id,
                    bool(info.success),
                    self._elapsed_s(t3),
                    getattr(info, "error", None),
                )

            # 5) Ensure exists + update current state on success
            logger.info(
                "[op=%s] HGW db upsert start target=%s via=%s serial=%s",
                op_id,
                hgw_ip,
                via_rpi_ip,
                getattr(info, "serial_number", None),
            )
            self.hgw_repo.upsert(
                hgw_ip,
                via_rpi_ip=via_rpi_ip,
                serial_number=info.serial_number,
                via_docker_container_id=dock,
            )

            if info.success:
                logger.info("[op=%s] HGW db update_from_fact start target=%s", op_id, hgw_ip)
                self.hgw_repo.update_from_fact(info)

            logger.info(
                "[op=%s] HGW reconnect end success=%s target=%s via=%s elapsed_s=%.3f model=%s sw=%s",
                op_id,
                bool(info.success),
                hgw_ip,
                via_rpi_ip,
                self._elapsed_s(started),
                getattr(info, "model_name", None),
                getattr(info, "software_version", None),
            )

            return {
                "success": bool(info.success),
                "target": hgw_ip,
                "via": via_rpi_ip,
                "elapsed_s": self._elapsed_s(started),
                "message": "HGW reconnected and collected"
                if info.success
                else (info.error or "HGW collect failed"),
                "details": {
                    "manufacturer": info.manufacturer,
                    "model_name": info.model_name,
                    "software_version": info.software_version,
                    "serial_number": info.serial_number,
                    "external_ip": info.external_ip,
                },
            }

        except Exception as e:
            logger.exception(
                "[op=%s] HGW reconnect crashed identifier=%s target=%s via=%s elapsed_s=%.3f err=%s",
                op_id,
                hgw_identifier,
                hgw_ip,
                via_rpi_ip,
                self._elapsed_s(started),
                e,
            )
            self.db.rollback()
            raise

        finally:
            self._safe_close("hgw_telnet_session", telnet_session, op_id=op_id)
            self._safe_close("hgw_session", hgw_session, op_id=op_id)
            self._safe_close("rpi_session", rpi_session, op_id=op_id)
            self._safe_close("bastion_session", bastion_session, op_id=op_id)