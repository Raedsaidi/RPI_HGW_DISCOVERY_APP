# app/services/rpi_reboot_service.py
from __future__ import annotations

import logging
import socket
import time
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.ssh_manager import SSHSession
from app.infrastructure.telnet_manager import NetgearTelnetSession
from app.repositories.rpi_repo import RpiRepository
from app.repositories.switch_repo import SwitchRepository

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────────────
POE_SHUTDOWN_WAIT_S: float = 4.0    # pause after "shutdown / power inline never"
POE_BOOT_WAIT_S:     float = 30.0   # time to give the RPi to boot before polling
SSH_POLL_INTERVAL_S: float = 5.0    # interval between SSH reachability probes
SSH_POLL_TIMEOUT_S:  float = 120.0  # give up waiting after this many seconds
SSH_CONNECT_TIMEOUT: int   = 15      # per-probe TCP timeout (seconds)
# ────────────────────────────────────────────────────────────────────────────


class RpiRebootService:
    """
    Hard-reboot a Raspberry Pi by cycling its PoE port on the parent switch.

    Steps
    -----
    1. Resolve RPi → switch_ip / switch_port from DB.
    2. Open bastion SSH, then Telnet to the switch.
    3. Execute the PoE-cycle sequence on the interface.
    4. Wait for the RPi to come back (TCP probe on port 22).
    5. Update ``last_seen`` / ``last_ssh_success`` in DB.
    """

    def __init__(self, db: Session):
        self.db = db
        self.rpi_repo    = RpiRepository(db)
        self.switch_repo = SwitchRepository(db)

    # ─────────────────────────────────────────────────────────────
    # Public entry-point
    # ─────────────────────────────────────────────────────────────

    def reboot_rpi(self, ip_mgmt: str) -> dict:
        op_id   = uuid4().hex[:10]
        started = time.perf_counter()

        logger.info("[op=%s] ── RPI REBOOT START ip_mgmt=%s", op_id, ip_mgmt)

        # ── 1. Resolve RPi record ──────────────────────────────
        rpi = self.rpi_repo.get_by_ip(ip_mgmt)
        if not rpi:
            logger.warning("[op=%s] RPI not found ip_mgmt=%s", op_id, ip_mgmt)
            raise ValueError(f"RPi not found: {ip_mgmt}")

        if not rpi.switch_ip or not rpi.switch_port:
            msg = (
                f"RPi {ip_mgmt} has no switch_ip/switch_port recorded — "
                "cannot perform PoE cycle."
            )
            logger.warning("[op=%s] %s", op_id, msg)
            raise ValueError(msg)

        logger.info(
            "[op=%s] RPi resolved switch_ip=%s switch_port=%s",
            op_id, rpi.switch_ip, rpi.switch_port,
        )

        # ── 2. Resolve switch credentials ─────────────────────
        sw = self.switch_repo.get_by_ip(rpi.switch_ip)
        if not sw:
            msg = f"Switch {rpi.switch_ip} not found in DB."
            logger.warning("[op=%s] %s", op_id, msg)
            raise ValueError(msg)

        bastion_session  = None
        telnet_session   = None

        try:
            # ── 3. Connect to bastion ──────────────────────────
            bastion_session, bastion_client = self._connect_bastion(op_id=op_id)

            # ── 4. Connect to switch via Telnet ────────────────
            logger.info(
                "[op=%s] SWITCH telnet connect start target=%s port=%s user=%s",
                op_id, sw.ip, sw.telnet_port, sw.telnet_user,
            )
            t0 = time.perf_counter()
            telnet_session = NetgearTelnetSession(
                switch_ip=sw.ip,
                switch_port=sw.telnet_port,
                username=sw.telnet_user,
                password=sw.telnet_pass,
                bastion_client=bastion_client,
                timeout=60,
            )
            ok, msg = telnet_session.connect()
            logger.info(
                "[op=%s] SWITCH telnet connect result ok=%s elapsed_s=%.3f msg=%s",
                op_id, ok, self._elapsed(t0), msg,
            )
            if not ok:
                return self._failure(op_id, ip_mgmt, started, f"Telnet connect failed: {msg}")

            # ── 5. PoE-cycle sequence ──────────────────────────
            poe_ok, poe_msg = self._poe_cycle(
                op_id=op_id,
                session=telnet_session,
                port=rpi.switch_port,
            )
            if not poe_ok:
                return self._failure(op_id, ip_mgmt, started, poe_msg)

            # ── 6. Wait for RPi to come back ───────────────────
            logger.info(
                "[op=%s] WAIT RPi boot — sleeping %.0fs before polling",
                op_id, POE_BOOT_WAIT_S,
            )
            time.sleep(POE_BOOT_WAIT_S)

            reachable = self._wait_for_ssh(op_id=op_id, ip=ip_mgmt)

            # ── 7. Update DB ───────────────────────────────────
            if reachable:
                logger.info(
                    "[op=%s] RPi is back — updating last_seen / last_ssh_success",
                    op_id,
                )
                rpi.last_seen        = datetime.utcnow()
                rpi.last_ssh_success = True
                rpi.last_ssh_error   = None
                self.db.commit()
            else:
                logger.warning(
                    "[op=%s] RPi did NOT come back within %.0fs after PoE cycle",
                    op_id, POE_BOOT_WAIT_S + SSH_POLL_TIMEOUT_S,
                )
                rpi.last_ssh_success = False
                rpi.last_ssh_error   = "RPi did not respond after PoE reboot"
                self.db.commit()

            elapsed = self._elapsed(started)
            logger.info(
                "[op=%s] ── RPI REBOOT END ip_mgmt=%s reachable=%s elapsed_s=%.3f",
                op_id, ip_mgmt, reachable, elapsed,
            )

            return {
                "success":   reachable,
                "target":    ip_mgmt,
                "switch_ip": sw.ip,
                "port":      rpi.switch_port,
                "elapsed_s": elapsed,
                "message": (
                    "RPi rebooted and is back online."
                    if reachable
                    else "PoE cycle executed but RPi did not respond in time."
                ),
            }

        except Exception as e:
            logger.exception(
                "[op=%s] RPI REBOOT crashed ip_mgmt=%s elapsed_s=%.3f err=%s",
                op_id, ip_mgmt, self._elapsed(started), e,
            )
            self.db.rollback()
            raise

        finally:
            self._safe_close("telnet_session",  telnet_session,  op_id=op_id)
            self._safe_close("bastion_session",  bastion_session, op_id=op_id)

    # ─────────────────────────────────────────────────────────────
    # PoE-cycle
    # ─────────────────────────────────────────────────────────────

    def _poe_cycle(
        self,
        op_id:   str,
        session: NetgearTelnetSession,
        port:    str,
    ) -> tuple[bool, str]:
        """
        Execute the PoE hard-reset sequence on *port*:

            config
            interface GigabitEthernet <port>
              shutdown
              power inline never
            exit
            interface GigabitEthernet <port>
              no shutdown
              power inline auto
            exit
        """
        logger.info(
            "[op=%s] POE CYCLE start switch=%s port=%s",
            op_id, session.switch_ip, port,
        )

        commands = [
            ("config",                          "enter config mode"),
            (f"interface GigabitEthernet {port}", "select interface"),
            ("shutdown",                          "shutdown interface"),
            ("power inline never",                "disable PoE"),
            ("exit",                              "exit interface"),
        ]

        for cmd, description in commands:
            ok, raw = self._exec_log(op_id, session, cmd, description)
            if not ok:
                return False, f"Command failed [{description}]: {raw}"

        logger.info(
            "[op=%s] POE CYCLE pause %.1fs (waiting for RPi to power off)",
            op_id, POE_SHUTDOWN_WAIT_S,
        )
        time.sleep(POE_SHUTDOWN_WAIT_S)

        restore_commands = [
            (f"interface GigabitEthernet {port}", "re-select interface"),
            ("no shutdown",                        "bring interface up"),
            ("power inline auto",                  "re-enable PoE"),
            ("exit",                               "exit interface"),
        ]

        for cmd, description in restore_commands:
            ok, raw = self._exec_log(op_id, session, cmd, description)
            if not ok:
                return False, f"Command failed [{description}]: {raw}"

        logger.info(
            "[op=%s] POE CYCLE complete — PoE restored on port %s",
            op_id, port,
        )
        return True, "PoE cycle completed"

    def _exec_log(
        self,
        op_id:   str,
        session: NetgearTelnetSession,
        cmd:     str,
        label:   str,
    ) -> tuple[bool, str]:
        """Execute one Telnet command and log both the command and its output."""
        logger.info("[op=%s]   >> %-30s  (cmd=%r)", op_id, label, cmd)
        t0 = time.perf_counter()
        ok, raw = session.execute(cmd)
        elapsed = self._elapsed(t0)

        # Log output compactly: first non-empty line or "(empty)"
        preview = next((l.strip() for l in raw.splitlines() if l.strip()), "(empty)")
        if ok:
            logger.info(
                "[op=%s]   << ok=True  elapsed_s=%.3f output=%r",
                op_id, elapsed, preview,
            )
        else:
            logger.warning(
                "[op=%s]   << ok=False elapsed_s=%.3f output=%r",
                op_id, elapsed, preview,
            )
        return ok, raw

    # ─────────────────────────────────────────────────────────────
    # Wait for SSH reachability
    # ─────────────────────────────────────────────────────────────

    def _wait_for_ssh(self, op_id: str, ip: str) -> bool:
        """
        Poll TCP port 22 on *ip* every SSH_POLL_INTERVAL_S seconds
        until the port accepts connections or SSH_POLL_TIMEOUT_S elapses.
        """
        deadline = time.time() + SSH_POLL_TIMEOUT_S
        attempt  = 0

        logger.info(
            "[op=%s] SSH POLL start ip=%s timeout=%.0fs interval=%.0fs",
            op_id, ip, SSH_POLL_TIMEOUT_S, SSH_POLL_INTERVAL_S,
        )

        while time.time() < deadline:
            attempt += 1
            remaining = round(deadline - time.time(), 1)
            try:
                with socket.create_connection((ip, 22), timeout=SSH_CONNECT_TIMEOUT):
                    logger.info(
                        "[op=%s] SSH POLL attempt=%d → port 22 OPEN (remaining=%.1fs)",
                        op_id, attempt, remaining,
                    )
                    return True
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                logger.debug(
                    "[op=%s] SSH POLL attempt=%d → not yet reachable (%s) remaining=%.1fs",
                    op_id, attempt, e, remaining,
                )

            time.sleep(SSH_POLL_INTERVAL_S)

        logger.warning(
            "[op=%s] SSH POLL exhausted after %d attempts — RPi still unreachable",
            op_id, attempt,
        )
        return False

    # ─────────────────────────────────────────────────────────────
    # Helpers (mirrors ReconnectService pattern)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _elapsed(started: float) -> float:
        return round(time.perf_counter() - started, 3)

    def _connect_bastion(self, *, op_id: str):
        import paramiko  # local import — already available via reconnect_service

        logger.info(
            "[op=%s] BASTION connect start host=%s user=%s",
            op_id, settings.PISERVER_HOST, settings.PISERVER_USER,
        )
        t0 = time.perf_counter()
        bastion = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        ok, msg = bastion.connect()
        logger.info(
            "[op=%s] BASTION connect result ok=%s elapsed_s=%.3f msg=%s",
            op_id, ok, self._elapsed(t0), msg,
        )
        if not ok or not bastion._client:
            self._safe_close("bastion", bastion, op_id=op_id)
            raise ConnectionError(f"Bastion SSH failed: {msg}")
        return bastion, bastion._client

    @staticmethod
    def _safe_close(name: str, obj, *, op_id: str) -> None:
        if not obj:
            return
        try:
            obj.close()
        except Exception:
            logger.exception("[op=%s] Failed to close %s", op_id, name)

    @staticmethod
    def _failure(op_id: str, ip: str, started: float, msg: str) -> dict:
        logger.warning("[op=%s] RPI REBOOT failed ip_mgmt=%s reason=%s", op_id, ip, msg)
        return {
            "success":   False,
            "target":    ip,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "message":   msg,
        }