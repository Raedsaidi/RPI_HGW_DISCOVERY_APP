import ipaddress
import time
from typing import Optional

import paramiko
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import (
    get_logger,
    log_hgw_collect,
    log_rpi_collect,
    log_ssh_connect,
    log_sync_end,
    log_sync_start,
    log_switch_collect,
)
from app.infrastructure.hgw_client import HgwClient, HgwCollectedData
from app.infrastructure.netgear_client import NetgearClient
from app.infrastructure.rpi_client import RpiClient
from app.infrastructure.ssh_manager import SSHPool, SSHSession
from app.infrastructure.telnet_manager import HgwTelnetSession, TelnetPool
from app.parsers.piserver_parser import parse_piserver
from app.repositories.discovery_repo import DiscoveryRepository
from app.repositories.hgw_repo import HgwRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.switch_repo import SwitchRepository
from app.services.email_service import EmailService

# Used for mini-update fallback operations (if repo methods not present)
from app.models.discovery_run import DiscoveryRun, DeviceError
from app.models.switch import SwitchMacEntry

logger = get_logger(__name__)


class DiscoveryService:
    """
    Orchestrates the full network discovery process:
      1. Connect to bastion (piserver)
      2. Read & parse /etc/dnsmasq.d/piserver
      3. Collect switch facts + MAC tables
      4. SSH to each RPi → collect metrics (including gateway IP + gateway MAC)
         and IMMEDIATELY:
         - collect HGW DeviceInfo via this RPi
         - persist HGW facts and update HGW table using serial_number when available

    + MINI UPDATE (same run_id):
      - given an HGW node (via_rpi_ips), resolve its switch
      - refresh this switch + its RPIs
      - immediately refresh HGWs behind those RPis
      - replace MAC table for that switch in the same run
      - clear DeviceError entries when devices become OK again
    """

    def __init__(self, db: Session):
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.switch_repo = SwitchRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.hgw_repo = HgwRepository(db)
        self.ssh_pool = SSHPool()
        self.telnet_pool = TelnetPool()
        self.email_service = EmailService()

    # ──────────────────────────────────────────────────────────
    # INTERNAL: mini-safe wrappers (repo may not yet implement them)
    # ──────────────────────────────────────────────────────────
    def _log_mini_plan(
        self,
        run_id: int,
        triggered_by: str,
        instance_key: Optional[str],
        hgw_ip: Optional[str],
        via_rpi_ips: list[str],
        switch_ip: Optional[str],
    ) -> None:
        # Optionnel: estimer combien de MAC entries on a déjà pour ce switch dans ce run
        mac_count = None
        rpi_ips_estimated: list[str] = []

        try:
            if switch_ip:
                entries = self.switch_repo.get_mac_entries_for_run(run_id, switch_ip=switch_ip)
                mac_count = len(entries)

                # tentative d’estimation: mapper MAC -> RPi.ip_mgmt via table rpis
                # (sans piserver snapshot, juste DB)
                for e in entries:
                    mac = (e.mac or "").upper()
                    r = self.rpi_repo.get_by_mac(mac) if hasattr(self.rpi_repo, "get_by_mac") else None
                    if r and r.ip_mgmt:
                        rpi_ips_estimated.append(r.ip_mgmt)
        except Exception:
            # ne jamais bloquer la mini-discovery à cause du log
            pass

        logger.info(
            "[DISCOVERY][MINI] PLAN run=%s by=%s target(instance_key=%s hgw_ip=%s) "
            "via_rpis=%s -> refresh switch=%s then RPis(on switch) then HGWs(behind those RPis). "
            "current_run_mac_entries_on_switch=%s estimated_rpis=%s",
            run_id,
            triggered_by,
            instance_key,
            hgw_ip,
            via_rpi_ips,
            switch_ip,
            mac_count,
            sorted(set(rpi_ips_estimated)) if rpi_ips_estimated else [],
            extra={
                "run_id": run_id,
                "action": "mini_plan",
                "triggered_by": triggered_by,
                "hgw_ip": hgw_ip,
                "instance_key": instance_key,
                "via_rpi_ips": via_rpi_ips,
                "switch_ip": switch_ip,
                "switch_mac_count_current_run": mac_count,
                "estimated_rpi_ips_current_run": sorted(set(rpi_ips_estimated)) if rpi_ips_estimated else [],
            },
        )

    def _mark_run_running(self, run_id: int, message: Optional[str] = None) -> None:
        fn = getattr(self.discovery_repo, "mark_run_running", None)
        if callable(fn):
            fn(run_id, message=message)
            return

        run = self.db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        if not run:
            return
        run.status = "running"
        run.finished_at = None
        if message is not None:
            run.message = message
        self.db.commit()

    def _mark_run_finished_simple(self, run_id: int, status: str, message: Optional[str] = None) -> None:
        fn = getattr(self.discovery_repo, "mark_run_finished_simple", None)
        if callable(fn):
            fn(run_id, status=status, message=message)
            return

        run = self.db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        if not run:
            return
        run.status = status
        from datetime import datetime

        run.finished_at = datetime.utcnow()
        if message is not None:
            run.message = message
        self.db.commit()

    def _compute_status_from_errors(self, run_id: int) -> str:
        fn = getattr(self.discovery_repo, "compute_status_from_errors", None)
        if callable(fn):
            return fn(run_id)

        cnt = self.db.query(DeviceError).filter(DeviceError.run_id == run_id).count()
        return "done" if cnt == 0 else "partial"

    def _clear_device_errors(self, run_id: int, device_type: str, device_ip: str) -> None:
        fn = getattr(self.discovery_repo, "clear_device_errors", None)
        if callable(fn):
            fn(run_id, device_type=device_type, device_ip=device_ip)
            return

        (
            self.db.query(DeviceError)
            .filter(DeviceError.run_id == run_id)
            .filter(DeviceError.device_type == device_type)
            .filter(DeviceError.device_ip == str(device_ip))
            .delete(synchronize_session=False)
        )
        self.db.commit()

    def _delete_switch_mac_entries_for_run(self, run_id: int, switch_ip: str) -> None:
        fn = getattr(self.switch_repo, "delete_mac_entries_for_run_switch", None)
        if callable(fn):
            fn(run_id, switch_ip)
            return

        (
            self.db.query(SwitchMacEntry)
            .filter(SwitchMacEntry.run_id == run_id)
            .filter(SwitchMacEntry.switch_ip == switch_ip)
            .delete(synchronize_session=False)
        )
        self.db.commit()

    def _cleanup_duplicate_rpi_macs_other_switches(self, run_id: int, keep_switch_ip: str, rpi_macs: set[str]) -> None:
        """Avoid same RPi showing on 2 switches in same run after a partial refresh."""
        if not rpi_macs:
            return

        (
            self.db.query(SwitchMacEntry)
            .filter(SwitchMacEntry.run_id == run_id)
            .filter(SwitchMacEntry.switch_ip != keep_switch_ip)
            .filter(SwitchMacEntry.mac.in_(list(rpi_macs)))
            .delete(synchronize_session=False)
        )
        self.db.commit()

    def _resolve_switch_ip_from_via_rpi_ips(
        self,
        run_id: int,
        via_rpi_ips: list[str],
        piserver_mac_to_ip: dict,
    ) -> Optional[str]:
        """
        Try multiple ways:
          1) rpis.switch_ip (only if RPi SSH succeeded at least once)
          2) switch_mac_entries for this run: (mac from piserver) -> switch_ip
        """
        if not via_rpi_ips:
            return None

        # Method 1: Rpi table
        for rip in via_rpi_ips:
            r = self.rpi_repo.get_by_ip(rip)
            if r and r.switch_ip:
                return r.switch_ip

        # Method 2: mac table in this run, using piserver ip->mac
        ip_to_mac = {ip: mac.upper() for mac, ip in piserver_mac_to_ip.items()}
        for rip in via_rpi_ips:
            mac = ip_to_mac.get(rip)
            if not mac:
                r = self.rpi_repo.get_by_ip(rip)
                mac = (r.mac.upper() if r and r.mac else None)
            if not mac:
                continue

            row = (
                self.db.query(SwitchMacEntry)
                .filter(SwitchMacEntry.run_id == run_id)
                .filter(SwitchMacEntry.mac == mac)
                .order_by(SwitchMacEntry.id.desc())
                .first()
            )
            if row:
                return row.switch_ip

        return None

    # ──────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT — FULL DISCOVERY
    # ──────────────────────────────────────────────────────────

    def run(self, triggered_by: str = "manual", run_id: Optional[int] = None) -> int:
        if run_id is None:
            run = self.discovery_repo.create_run(triggered_by=triggered_by)
            run_id = run.id
        else:
            run = self.discovery_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Run {run_id} not found")

        run_start = time.perf_counter()
        log_sync_start(logger, run_id, triggered_by)

        counters = {
            "switches_ok": 0,
            "switches_err": 0,
            "rpis_ok": 0,
            "rpis_err": 0,
            "hgws_ok": 0,
            "hgws_err": 0,
        }

        bastion_session: Optional[SSHSession] = None
        bastion_client: Optional[paramiko.SSHClient] = None

        try:
            # STEP 1: Connect to Bastion
            bastion_session, bastion_client = self._connect_bastion(run_id)
            if bastion_session is None:
                total_elapsed = time.perf_counter() - run_start
                log_sync_end(logger, run_id, "error", total_elapsed, counters)
                return run_id

            # STEP 2: Read piserver file
            piserver_mac_to_ip = self._read_piserver(run_id, bastion_session)
            if piserver_mac_to_ip is None:
                total_elapsed = time.perf_counter() - run_start
                log_sync_end(logger, run_id, "error", total_elapsed, counters)
                return run_id

            piserver_macs = set(piserver_mac_to_ip.keys())

            # STEP 3: Process switches
            rpi_to_switch = self._process_switches(
                run_id=run_id,
                bastion_client=bastion_client,
                piserver_macs=piserver_macs,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

            # STEP 4: Process RPis + immediately collect HGWs behind them
            self._process_rpis(
                run_id=run_id,
                bastion_client=bastion_client,
                rpi_to_switch=rpi_to_switch,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

        except Exception as e:
            logger.error(
                "[DISCOVERY] Unexpected error in run #%d: %s",
                run_id,
                e,
                exc_info=True,
                extra={"run_id": run_id, "action": "discovery_fatal_error"},
            )
            self.discovery_repo.save_error(run_id, "discovery", "global", "fatal", str(e))

        finally:
            self._cleanup(bastion_session)

        # Finish run
        total_elapsed = time.perf_counter() - run_start
        total_errors = counters["switches_err"] + counters["rpis_err"] + counters["hgws_err"]
        status = "done" if total_errors == 0 else "partial"
        msg = None if total_errors == 0 else (
            f"Completed with errors: "
            f"sw_err={counters['switches_err']}, "
            f"rpi_err={counters['rpis_err']}, "
            f"hgw_err={counters['hgws_err']}"
        )

        self.discovery_repo.finish_run(run_id, status=status, message=msg, **counters)
        log_sync_end(logger, run_id, status, total_elapsed, counters)
        # ── Rapport email aux ADMINs ─────────────────────────
        try:
            errors = self.discovery_repo.get_errors_for_run(run_id)
            self.email_service.send_discovery_report(
                run_id=run_id,
                status=status,
                triggered_by=triggered_by,
                counters=counters,
                errors=errors,
                elapsed_s=total_elapsed,
            )
        except Exception as e:
            # Jamais bloquant
            logger.error(
                "[EMAIL] Failed to send report for run #%d: %s",
                run_id,
                e,
                exc_info=True,
                extra={"run_id": run_id, "action": "email_report_failed"},
            )
        # ────────────────────────────────────────────────────
        return run_id

    # ──────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT — MINI UPDATE (same run_id)
    # ──────────────────────────────────────────────────────────

    def run_mini_hgw_update(
        self,
        run_id: int,
        triggered_by: str = "manual",
        via_rpi_ips: Optional[list[str]] = None,
        instance_key: Optional[str] = None,
        hgw_ip: Optional[str] = None,
    ) -> int:
        """
        Update partial topology data for the same run_id:
        - resolve switch ip from via_rpi_ips
        - refresh that switch (facts + replace MAC table for this run)
        - refresh all RPis found on that switch
        - immediately refresh all HGWs behind those RPis
        - clear errors on success so UI turns green
        """
        run = self.discovery_repo.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        via_rpi_ips = via_rpi_ips or []
        label = instance_key or hgw_ip or (via_rpi_ips[0] if via_rpi_ips else "unknown")

        # ✅ PLAN LOG (before any network connection)
        # Best-effort guess of switch_ip from DB (no SSH/Telnet needed)
        switch_ip_guess: Optional[str] = None
        try:
            for rip in via_rpi_ips:
                r = self.rpi_repo.get_by_ip(rip)
                if r and r.switch_ip:
                    switch_ip_guess = r.switch_ip
                    break
        except Exception:
            # never block mini discovery because of logging
            switch_ip_guess = None

        logger.info(
            "[DISCOVERY][MINI] PLAN run_id=%s label=%s by=%s target(hgw_ip=%s instance_key=%s) "
            "via_rpis=%s -> steps: connect bastion, read piserver, resolve switch, "
            "refresh switch (facts+REPLACE mac table), refresh RPis on that switch, refresh HGWs behind those RPis. "
            "switch_ip_guess(db)=%s",
            run_id,
            label,
            triggered_by,
            hgw_ip,
            instance_key,
            via_rpi_ips,
            switch_ip_guess,
            extra={
                "run_id": run_id,
                "action": "mini_plan",
                "triggered_by": triggered_by,
                "label": label,
                "hgw_ip": hgw_ip,
                "instance_key": instance_key,
                "via_rpi_ips": via_rpi_ips,
                "switch_ip_guess": switch_ip_guess,
            },
        )

        self._mark_run_running(run_id, message=f"Mini update started for {label} by {triggered_by}")

        counters = {
            "switches_ok": 0,
            "switches_err": 0,
            "rpis_ok": 0,
            "rpis_err": 0,
            "hgws_ok": 0,
            "hgws_err": 0,
        }

        bastion_session: Optional[SSHSession] = None
        bastion_client: Optional[paramiko.SSHClient] = None

        try:
            bastion_session, bastion_client = self._connect_bastion_mini(run_id)
            if bastion_session is None:
                status = self._compute_status_from_errors(run_id)
                self._mark_run_finished_simple(run_id, status=status, message="Mini update failed: bastion SSH")
                return run_id

            piserver_mac_to_ip = self._read_piserver_mini(run_id, bastion_session)
            if piserver_mac_to_ip is None:
                status = self._compute_status_from_errors(run_id)
                self._mark_run_finished_simple(run_id, status=status, message="Mini update failed: piserver read")
                return run_id

            switch_ip = self._resolve_switch_ip_from_via_rpi_ips(run_id, via_rpi_ips, piserver_mac_to_ip)
            if not switch_ip:
                raise ValueError("Mini update: cannot resolve switch_ip from via_rpi_ips")

            # Optional: log if DB guess differs from resolved switch
            if switch_ip_guess and switch_ip_guess != switch_ip:
                logger.info(
                    "[DISCOVERY][MINI] PLAN resolved switch_ip differs from DB guess: guess=%s resolved=%s",
                    switch_ip_guess,
                    switch_ip,
                    extra={
                        "run_id": run_id,
                        "action": "mini_plan_switch_resolved",
                        "switch_ip_guess": switch_ip_guess,
                        "switch_ip": switch_ip,
                    },
                )

            piserver_macs = set(piserver_mac_to_ip.keys())

            # refresh only the switch of interest (replace MAC table)
            rpi_to_switch = self._process_switch_single_replace_macs(
                run_id=run_id,
                bastion_client=bastion_client,
                switch_ip=switch_ip,
                piserver_macs=piserver_macs,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

            # refresh RPis and immediately refresh HGWs behind them
            self._process_rpis(
                run_id=run_id,
                bastion_client=bastion_client,
                rpi_to_switch=rpi_to_switch,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

        except Exception as e:
            logger.error("[DISCOVERY] Mini update failed: %s", e, exc_info=True, extra={"run_id": run_id})
            self.discovery_repo.save_error(run_id, "mini", label, "fatal", str(e))

        finally:
            self._cleanup(bastion_session)

        status = self._compute_status_from_errors(run_id)
        self._mark_run_finished_simple(run_id, status=status, message=f"Mini update finished for {label}")
        return run_id

    # ──────────────────────────────────────────────────────────
    # STEP 1: BASTION CONNECTION
    # ──────────────────────────────────────────────────────────

    def _connect_bastion(self, run_id: int) -> tuple[Optional[SSHSession], Optional[paramiko.SSHClient]]:
        logger.info(
            "[DISCOVERY] Connecting to bastion %s (user=%s)",
            settings.PISERVER_HOST,
            settings.PISERVER_USER,
            extra={"run_id": run_id, "device_ip": settings.PISERVER_HOST, "action": "bastion_connect"},
        )
        start = time.perf_counter()

        bastion_session = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        ok, msg = bastion_session.connect()
        elapsed = time.perf_counter() - start

        log_ssh_connect(
            logger,
            host=settings.PISERVER_HOST,
            user=settings.PISERVER_USER,
            success=ok,
            elapsed_s=elapsed,
            error=msg if not ok else None,
        )

        if not ok:
            logger.error(
                "[DISCOVERY] ✗ Bastion connection failed: %s",
                msg,
                extra={"run_id": run_id, "action": "bastion_connect_failed"},
            )
            self.discovery_repo.save_error(run_id, "piserver", settings.PISERVER_HOST, "ssh", msg)
            self.discovery_repo.finish_run(run_id, status="error", message=f"Bastion SSH failed: {msg}")
            return None, None

        bastion_client = bastion_session._client
        return bastion_session, bastion_client

    def _connect_bastion_mini(self, run_id: int) -> tuple[Optional[SSHSession], Optional[paramiko.SSHClient]]:
        """Same as _connect_bastion but does NOT finish_run(error) on failure."""
        bastion_session = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        ok, msg = bastion_session.connect()
        if not ok:
            self.discovery_repo.save_error(run_id, "piserver", settings.PISERVER_HOST, "ssh", msg)
            return None, None
        return bastion_session, bastion_session._client

    # ──────────────────────────────────────────────────────────
    # STEP 2: READ PISERVER FILE
    # ──────────────────────────────────────────────────────────

    def _read_piserver(self, run_id: int, bastion_session: SSHSession) -> Optional[dict]:
        logger.info(
            "[DISCOVERY] Reading piserver file: %s",
            settings.PISERVER_FILE,
            extra={"run_id": run_id, "action": "read_piserver", "device_ip": settings.PISERVER_HOST},
        )
        start = time.perf_counter()

        ok, content = bastion_session.execute(f"cat {settings.PISERVER_FILE}", timeout=60)
        elapsed = time.perf_counter() - start

        if not ok or not content.strip():
            logger.error(
                "[DISCOVERY] ✗ Failed to read piserver file (%.2fs): %s",
                elapsed,
                content,
                extra={"run_id": run_id, "action": "read_piserver_failed"},
            )
            self.discovery_repo.save_error(
                run_id, "piserver", settings.PISERVER_HOST, "read_file", content or "Empty response"
            )
            self.discovery_repo.finish_run(run_id, status="error", message="Cannot read piserver file")
            return None

        self.discovery_repo.save_piserver_snapshot(run_id, content)

        rpi_entries = parse_piserver(content)
        for entry in rpi_entries:
            self.rpi_repo.upsert(entry.mac, entry.ip_mgmt, entry.label, entry.group)

        mac_to_ip = {e.mac: e.ip_mgmt for e in rpi_entries}

        logger.info(
            "[DISCOVERY] ✓ Piserver parsed: %d active RPi entries (%.2fs)",
            len(rpi_entries),
            elapsed,
            extra={
                "run_id": run_id,
                "action": "piserver_parsed",
                "rpi_count": len(rpi_entries),
                "elapsed_s": round(elapsed, 3),
            },
        )
        return mac_to_ip

    def _read_piserver_mini(self, run_id: int, bastion_session: SSHSession) -> Optional[dict]:
        ok, content = bastion_session.execute(f"cat {settings.PISERVER_FILE}", timeout=60)
        if not ok or not content.strip():
            self.discovery_repo.save_error(
                run_id, "piserver", settings.PISERVER_HOST, "read_file", content or "Empty response"
            )
            return None

        # If piserver is now readable, clear previous piserver error for this run
        self._clear_device_errors(run_id, "piserver", settings.PISERVER_HOST)

        self.discovery_repo.save_piserver_snapshot(run_id, content)

        rpi_entries = parse_piserver(content)
        for entry in rpi_entries:
            self.rpi_repo.upsert(entry.mac, entry.ip_mgmt, entry.label, entry.group)

        return {e.mac.upper(): e.ip_mgmt for e in rpi_entries}

    # ──────────────────────────────────────────────────────────
    # STEP 3: PROCESS SWITCHES
    # ──────────────────────────────────────────────────────────

    def _process_switches(
        self,
        run_id: int,
        bastion_client: paramiko.SSHClient,
        piserver_macs: set,
        piserver_mac_to_ip: dict,
        counters: dict,
    ) -> dict:
        switches = self.switch_repo.list_all(enabled_only=True)

        if not switches:
            logger.warning(
                "[DISCOVERY] No enabled switches found in DB.",
                extra={"run_id": run_id, "action": "no_switches"},
            )
            return {}

        logger.info(
            "[DISCOVERY] Processing %d switches",
            len(switches),
            extra={"run_id": run_id, "action": "switches_start", "count": len(switches)},
        )

        rpi_to_switch: dict[str, tuple[str, str]] = {}

        for sw in switches:
            sw_start = time.perf_counter()
            logger.info(
                "[DISCOVERY] ─── Switch %s (%s) ───",
                sw.ip,
                sw.name or "unnamed",
                extra={"run_id": run_id, "switch_ip": sw.ip, "action": "switch_start"},
            )

            try:
                telnet_sess = self.telnet_pool.get_or_create(
                    switch_ip=sw.ip,
                    switch_port=sw.telnet_port,
                    username=sw.telnet_user,
                    password=sw.telnet_pass,
                    bastion_client=bastion_client,
                    timeout=60,
                )

                if not telnet_sess.connected:
                    ok_conn, conn_msg = telnet_sess.connect()
                    if not ok_conn:
                        raise ConnectionError(f"Telnet connection failed: {conn_msg}")

                client = NetgearClient(telnet_sess)
                data = client.collect_all()

                if not data.success:
                    raise Exception(data.error or "collect_all() failed")

                # Clear switch error if it was previously failing in same run (rare but harmless)
                self._clear_device_errors(run_id, "switch", sw.ip)

                self.switch_repo.save_fact(run_id, sw.ip, data)

                filtered_mac_entries = [
                    entry
                    for entry in data.mac_entries
                    if sw.port_management is None or entry.port != sw.port_management
                ]

                rpi_count_on_switch = 0
                for entry in filtered_mac_entries:
                    self.switch_repo.save_mac_entry(run_id, sw.ip, entry)

                    mac_upper = (entry.mac or "").upper()
                    if mac_upper in piserver_macs:
                        rpi_ip = piserver_mac_to_ip[mac_upper]
                        rpi_to_switch[rpi_ip] = (sw.ip, entry.port)
                        rpi_count_on_switch += 1

                sw_elapsed = time.perf_counter() - sw_start
                log_switch_collect(
                    logger,
                    switch_ip=sw.ip,
                    run_id=run_id,
                    mac_count=len(filtered_mac_entries),
                    rpi_count=rpi_count_on_switch,
                    elapsed_s=sw_elapsed,
                    success=True,
                )
                counters["switches_ok"] += 1

            except Exception as e:
                sw_elapsed = time.perf_counter() - sw_start
                log_switch_collect(
                    logger,
                    switch_ip=sw.ip,
                    run_id=run_id,
                    mac_count=0,
                    rpi_count=0,
                    elapsed_s=sw_elapsed,
                    success=False,
                    error=str(e),
                )
                self.discovery_repo.save_error(run_id, "switch", sw.ip, "collect", str(e))
                counters["switches_err"] += 1
                continue

        logger.info(
            "[DISCOVERY] Switches done: ok=%d err=%d, %d RPis identified",
            counters["switches_ok"],
            counters["switches_err"],
            len(rpi_to_switch),
            extra={
                "run_id": run_id,
                "action": "switches_done",
                "rpi_identified": len(rpi_to_switch),
            },
        )
        return rpi_to_switch

    def _process_switch_single_replace_macs(
        self,
        run_id: int,
        bastion_client: paramiko.SSHClient,
        switch_ip: str,
        piserver_macs: set,
        piserver_mac_to_ip: dict,
        counters: dict,
    ) -> dict:
        """
        Mini-update switch processing:
          - refresh facts
          - REPLACE MAC entries for (run_id, switch_ip)
          - cleanup duplicate RPi MACs from other switches in same run
        """
        sw = self.switch_repo.get_by_ip(switch_ip)
        if not sw or not sw.enabled:
            raise ValueError(f"Switch {switch_ip} not found or disabled")

        rpi_to_switch: dict[str, tuple[str, str]] = {}

        sw_start = time.perf_counter()
        logger.info(
            "[DISCOVERY] ─── MINI Switch %s (%s) ───",
            sw.ip,
            sw.name or "unnamed",
            extra={"run_id": run_id, "switch_ip": sw.ip, "action": "switch_mini_start"},
        )

        try:
            telnet_sess = self.telnet_pool.get_or_create(
                switch_ip=sw.ip,
                switch_port=sw.telnet_port,
                username=sw.telnet_user,
                password=sw.telnet_pass,
                bastion_client=bastion_client,
                timeout=60,
            )

            if not telnet_sess.connected:
                ok_conn, conn_msg = telnet_sess.connect()
                if not ok_conn:
                    raise ConnectionError(f"Telnet connection failed: {conn_msg}")

            client = NetgearClient(telnet_sess)
            data = client.collect_all()
            if not data.success:
                raise Exception(data.error or "collect_all() failed")

            # Switch OK => clear old error
            self._clear_device_errors(run_id, "switch", sw.ip)

            self.switch_repo.save_fact(run_id, sw.ip, data)

            filtered_mac_entries = [
                entry
                for entry in data.mac_entries
                if sw.port_management is None or entry.port != sw.port_management
            ]

            # Determine which RPi MACs are on this switch (to cleanup global duplicates)
            rpi_macs_seen: set[str] = set()
            rpi_count_on_switch = 0
            for entry in filtered_mac_entries:
                mac_upper = (entry.mac or "").upper()
                if mac_upper in piserver_macs:
                    rpi_macs_seen.add(mac_upper)
                    rpi_ip = piserver_mac_to_ip[mac_upper]
                    rpi_to_switch[rpi_ip] = (sw.ip, entry.port)
                    rpi_count_on_switch += 1

            # Replace MAC entries for this switch in this run
            self._delete_switch_mac_entries_for_run(run_id, sw.ip)
            for entry in filtered_mac_entries:
                self.switch_repo.save_mac_entry(run_id, sw.ip, entry)

            # Avoid RPi duplicates across switches in this run
            self._cleanup_duplicate_rpi_macs_other_switches(run_id, sw.ip, rpi_macs_seen)

            sw_elapsed = time.perf_counter() - sw_start
            log_switch_collect(
                logger,
                switch_ip=sw.ip,
                run_id=run_id,
                mac_count=len(filtered_mac_entries),
                rpi_count=rpi_count_on_switch,
                elapsed_s=sw_elapsed,
                success=True,
            )
            counters["switches_ok"] += 1

        except Exception as e:
            sw_elapsed = time.perf_counter() - sw_start
            log_switch_collect(
                logger,
                switch_ip=sw.ip,
                run_id=run_id,
                mac_count=0,
                rpi_count=0,
                elapsed_s=sw_elapsed,
                success=False,
                error=str(e),
            )
            self.discovery_repo.save_error(run_id, "switch", sw.ip, "collect", str(e))
            counters["switches_err"] += 1
            return {}

        return rpi_to_switch

    # ──────────────────────────────────────────────────────────
    # STEP 4: PROCESS RPIs + IMMEDIATE HGW COLLECTION
    # ──────────────────────────────────────────────────────────

    def _process_rpis(
        self,
        run_id: int,
        bastion_client: paramiko.SSHClient,
        rpi_to_switch: dict,
        piserver_mac_to_ip: dict,
        counters: dict,
    ) -> None:
        """
        For each RPi discovered on switches:
          - SSH into the RPi via bastion, collect metrics
          - persist RPi facts and connectivity info
          - if an HGW IP is found, immediately collect HGW DeviceInfo via this RPi
            and persist HGW facts + update topology.

        Also updates counters["rpis_*"] and counters["hgws_*"].
        """
        rpi_ips = sorted(rpi_to_switch.keys(), key=ipaddress.ip_address)

        if not rpi_ips:
            logger.warning(
                "[DISCOVERY] No RPis found on any switch for run #%d",
                run_id,
                extra={"run_id": run_id, "action": "no_rpis_found"},
            )
            return

        logger.info(
            "[DISCOVERY] Processing %d RPis",
            len(rpi_ips),
            extra={"run_id": run_id, "action": "rpis_start", "count": len(rpi_ips)},
        )

        ip_to_mac = {ip: mac for mac, ip in piserver_mac_to_ip.items()}

        # Pour éviter de compter plusieurs fois le même HGW (N RPis derrière 1 HGW)
        # on garde un set d'instance_keys déjà traités dans ce run.
        hgws_seen_instance_keys: set[str] = set()

        for rpi_ip in rpi_ips:
            switch_ip, switch_port = rpi_to_switch[rpi_ip]
            rpi_mac = ip_to_mac.get(rpi_ip)
            rpi_start = time.perf_counter()

            logger.info(
                "[DISCOVERY] ─── RPi %s (switch=%s port=%s) ───",
                rpi_ip,
                switch_ip,
                switch_port,
                extra={
                    "run_id": run_id,
                    "rpi_ip": rpi_ip,
                    "switch_ip": switch_ip,
                    "action": "rpi_start",
                },
            )

            try:
                rpi_session, used_user = self._connect_rpi_with_fallback(
                    rpi_ip=rpi_ip,
                    bastion_client=bastion_client,
                    run_id=run_id,
                )

                if rpi_session is None:
                    raise ConnectionError(f"All SSH credentials failed for {rpi_ip}")

                rpi_client = RpiClient(rpi_session)
                collected = rpi_client.collect_all(rpi_ip)

                # ✅ RPi OK => clear old error
                self._clear_device_errors(run_id, "rpi", rpi_ip)

                self.rpi_repo.save_fact(run_id, rpi_mac, collected)

                self.rpi_repo.update_ssh_status(
                    ip_mgmt=rpi_ip,
                    success=True,
                    switch_ip=switch_ip,
                    switch_port=switch_port,
                    hgw_ip=collected.hgw_ip,
                )

                rpi_elapsed = time.perf_counter() - rpi_start
                log_rpi_collect(
                    logger,
                    rpi_ip=rpi_ip,
                    run_id=run_id,
                    hostname=collected.hostname or "",
                    hgw_ip=collected.hgw_ip,
                    elapsed_s=rpi_elapsed,
                    success=True,
                )
                counters["rpis_ok"] += 1

                # ── HGW immédiat si présent ─────────────────────────────
                if collected.hgw_ip:
                    gw_mac = getattr(collected, "hgw_gateway_mac", None)
                    if gw_mac:
                        instance_key = gw_mac.upper()
                    else:
                        instance_key = f"{switch_ip}|{collected.hgw_ip}"

                    if instance_key in hgws_seen_instance_keys:
                        logger.info(
                            "[DISCOVERY] HGW %s (instance=%s) already processed, skipping extra collection via RPi %s",
                            collected.hgw_ip,
                            instance_key,
                            rpi_ip,
                            extra={
                                "run_id": run_id,
                                "hgw_ip": collected.hgw_ip,
                                "instance_key": instance_key,
                                "rpi_ip": rpi_ip,
                                "action": "hgw_skip_duplicate",
                            },
                        )
                    else:
                        hgws_seen_instance_keys.add(instance_key)
                        self._collect_hgw_for_rpi(
                            run_id=run_id,
                            hgw_ip=collected.hgw_ip,
                            via_rpi_ip=rpi_ip,
                            switch_ip=switch_ip,
                            instance_key=instance_key,
                            rpi_session=rpi_session,
                            counters=counters,
                            via_docker_container_id=collected.hgw_via_docker_container,
                        )

            except ConnectionError as e:
                rpi_elapsed = time.perf_counter() - rpi_start
                log_rpi_collect(
                    logger,
                    rpi_ip=rpi_ip,
                    run_id=run_id,
                    hostname="",
                    hgw_ip=None,
                    elapsed_s=rpi_elapsed,
                    success=False,
                    error=str(e),
                )
                self.discovery_repo.save_error(run_id, "rpi", rpi_ip, "ssh", str(e))
                self.rpi_repo.update_ssh_status(rpi_ip, success=False, error=str(e))
                counters["rpis_err"] += 1

            except Exception as e:
                rpi_elapsed = time.perf_counter() - rpi_start
                log_rpi_collect(
                    logger,
                    rpi_ip=rpi_ip,
                    run_id=run_id,
                    hostname="",
                    hgw_ip=None,
                    elapsed_s=rpi_elapsed,
                    success=False,
                    error=str(e),
                )
                self.discovery_repo.save_error(run_id, "rpi", rpi_ip, "collect", str(e))
                self.rpi_repo.update_ssh_status(rpi_ip, success=False, error=str(e))
                counters["rpis_err"] += 1

        logger.info(
            "[DISCOVERY] RPis done: rpis_ok=%d rpis_err=%d hgws_ok=%d hgws_err=%d",
            counters["rpis_ok"],
            counters["rpis_err"],
            counters["hgws_ok"],
            counters["hgws_err"],
            extra={"run_id": run_id, "action": "rpis_done"},
        )

    # ──────────────────────────────────────────────────────────
    # HGW COLLECTION (per RPi, immédiat)
    # ──────────────────────────────────────────────────────────

    def _collect_hgw_for_rpi(
        self,
        run_id: int,
        hgw_ip: str,
        via_rpi_ip: str,
        switch_ip: str,
        instance_key: str,
        rpi_session: SSHSession,
        counters: dict,
        via_docker_container_id: Optional[str] = None,
    ) -> None:
        """
        Collecte les infos HGW via un RPi donné, immédiatement après la collecte RPi.
        Utilise instance_key (gateway MAC ou switch_ip|hgw_ip) pour:
          - HgwFact.instance_key
          - DeviceError.device_ip pour le type "hgw"
        """
        hgw_start = time.perf_counter()

        logger.info(
            "[DISCOVERY] ─── HGW %s (instance=%s, via=%s, switch=%s) ───",
            hgw_ip,
            instance_key,
            via_rpi_ip,
            switch_ip,
            extra={
                "run_id": run_id,
                "hgw_ip": hgw_ip,
                "instance_key": instance_key,
                "rpi_ip": via_rpi_ip,
                "switch_ip": switch_ip,
                "action": "hgw_start",
            },
        )

        collected_data: Optional[HgwCollectedData] = None
        last_error: Optional[str] = None
        dock = (via_docker_container_id or "").strip() or None

        try:
            rpi_client_obj = rpi_session._client

            hgw_session = self.ssh_pool.get_or_create(
                host=hgw_ip,
                username=settings.HGW_SSH_USER,
                password=settings.HGW_SSH_PASS,
                port=22,
                tunnel=rpi_client_obj,
                tunnel_via_docker_container=dock,
                timeout=60,
            )
            hgw_conn = hgw_session
            telnet_fallback: Optional[HgwTelnetSession] = None

            try:
                if not hgw_session.connected:
                    connect_start = time.perf_counter()
                    ok_h, err_h = hgw_session.connect()
                    connect_elapsed = time.perf_counter() - connect_start

                    log_ssh_connect(
                        logger,
                        host=hgw_ip,
                        user=settings.HGW_SSH_USER,
                        success=ok_h,
                        elapsed_s=connect_elapsed,
                        error=err_h if not ok_h else None,
                        via=via_rpi_ip,
                    )

                    if not ok_h:
                        telnet_fallback = HgwTelnetSession(
                            hgw_ip=hgw_ip,
                            hgw_port=settings.HGW_TELNET_PORT,
                            username=settings.HGW_SSH_USER,
                            password=settings.HGW_SSH_PASS,
                            tunnel_client=rpi_client_obj,
                            timeout=60,
                            tunnel_via_docker_container=dock,
                        )
                        ok_t, err_t = telnet_fallback.connect()
                        if not ok_t:
                            raise ConnectionError(f"HGW SSH failed: {err_h}; Telnet failed: {err_t}")
                        hgw_conn = telnet_fallback

                hgw_client = HgwClient(hgw_conn)
                hgw_data = hgw_client.collect_deviceinfo(hgw_ip, via_rpi_ip)

                # Attacher l'instance_key pour la persistance + topologie
                setattr(hgw_data, "instance_key", instance_key)
                hgw_data.via_docker_container_id = dock

                collected_data = hgw_data

            finally:
                if telnet_fallback is not None:
                    telnet_fallback.close()

        except Exception as e:
            last_error = str(e)
            logger.warning(
                "[DISCOVERY] HGW %s (instance=%s, via=%s) collection failed: %s",
                hgw_ip,
                instance_key,
                via_rpi_ip,
                e,
                extra={
                    "run_id": run_id,
                    "hgw_ip": hgw_ip,
                    "instance_key": instance_key,
                    "rpi_ip": via_rpi_ip,
                    "action": "hgw_collect_failed",
                },
            )

        hgw_elapsed = time.perf_counter() - hgw_start

        if collected_data is None:
            log_hgw_collect(
                logger,
                hgw_ip=hgw_ip,
                via_rpi=via_rpi_ip,
                run_id=run_id,
                model=None,
                elapsed_s=hgw_elapsed,
                success=False,
                error=last_error or "HGW unreachable via RPi",
            )
            self.discovery_repo.save_error(
                run_id,
                "hgw",
                instance_key,
                "ssh",
                last_error or "HGW unreachable via RPi",
            )
            counters["hgws_err"] += 1
            return

        # Persist fact (includes instance_key)
        self.hgw_repo.save_fact(run_id, collected_data)

        if collected_data.success:
            # ✅ HGW OK => clear old errors pour cette instance_key
            self._clear_device_errors(run_id, "hgw", instance_key)

            # Upsert HGW principal en utilisant le serial si dispo
            self.hgw_repo.upsert(
                collected_data.hgw_ip,
                via_rpi_ip=collected_data.via_rpi_ip,
                serial_number=collected_data.serial_number,
                via_docker_container_id=collected_data.via_docker_container_id,
            )

            # Mise à jour des champs HGW à partir du fact
            self.hgw_repo.update_from_fact(collected_data)

            log_hgw_collect(
                logger,
                hgw_ip=hgw_ip,
                via_rpi=collected_data.via_rpi_ip,
                run_id=run_id,
                model=collected_data.model_name,
                elapsed_s=hgw_elapsed,
                success=True,
            )
            counters["hgws_ok"] += 1
        else:
            log_hgw_collect(
                logger,
                hgw_ip=hgw_ip,
                via_rpi=collected_data.via_rpi_ip,
                run_id=run_id,
                model=None,
                elapsed_s=hgw_elapsed,
                success=False,
                error=collected_data.error,
            )
            self.discovery_repo.save_error(
                run_id,
                "hgw",
                instance_key,
                "ba_cli",
                collected_data.error or "ba-cli returned no data",
            )
            counters["hgws_err"] += 1

    # ──────────────────────────────────────────────────────────
    # HELPERS — CREDENTIALS & SSH
    # ──────────────────────────────────────────────────────────

    def _build_credentials_chain(self, rpi_ip: str) -> list[tuple[str, str]]:
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

    def _connect_rpi_with_fallback(
        self,
        rpi_ip: str,
        bastion_client: paramiko.SSHClient,
        run_id: int,
    ) -> tuple[Optional[SSHSession], Optional[str]]:
        credentials_chain = self._build_credentials_chain(rpi_ip)

        for attempt, (ssh_user, ssh_pass) in enumerate(credentials_chain, start=1):
            rpi_session = self.ssh_pool.get_or_create(
                host=rpi_ip,
                username=ssh_user,
                password=ssh_pass,
                port=22,
                tunnel=bastion_client,
                timeout=60,
            )

            if rpi_session.connected:
                return rpi_session, ssh_user

            connect_start = time.perf_counter()
            ok, err_msg = rpi_session.connect()
            connect_elapsed = time.perf_counter() - connect_start

            log_ssh_connect(
                logger,
                host=rpi_ip,
                user=ssh_user,
                success=ok,
                elapsed_s=connect_elapsed,
                error=err_msg if not ok else None,
                via=settings.PISERVER_HOST,
            )

            if ok:
                logger.info(
                    "[DISCOVERY] ✓ RPi %s connected with user=%s (attempt %d/%d, %.2fs)",
                    rpi_ip,
                    ssh_user,
                    attempt,
                    len(credentials_chain),
                    connect_elapsed,
                    extra={
                        "run_id": run_id,
                        "rpi_ip": rpi_ip,
                        "ssh_user": ssh_user,
                        "attempt": attempt,
                        "action": "rpi_ssh_ok",
                    },
                )
                return rpi_session, ssh_user

            logger.warning(
                "[DISCOVERY] ✗ RPi %s SSH failed with user=%s (attempt %d/%d): %s",
                rpi_ip,
                ssh_user,
                attempt,
                len(credentials_chain),
                err_msg,
                extra={
                    "run_id": run_id,
                    "rpi_ip": rpi_ip,
                    "ssh_user": ssh_user,
                    "attempt": attempt,
                    "action": "rpi_ssh_attempt_failed",
                },
            )

        logger.error(
            "[DISCOVERY] ✗ RPi %s — All %d SSH credential attempts failed",
            rpi_ip,
            len(credentials_chain),
            extra={
                "run_id": run_id,
                "rpi_ip": rpi_ip,
                "action": "rpi_all_credentials_failed",
                "attempts": len(credentials_chain),
            },
        )
        return None, None

    def _get_rpi_session(
        self,
        rpi_ip: str,
        bastion_client: paramiko.SSHClient,
        run_id: int,
    ) -> Optional[SSHSession]:
        """
        Gardé pour compatibilité potentielle.
        Aujourd'hui on réutilise la session déjà ouverte dans _process_rpis,
        donc cette méthode n'est plus utilisée dans le flux principal.
        """
        session, _ = self._connect_rpi_with_fallback(
            rpi_ip=rpi_ip,
            bastion_client=bastion_client,
            run_id=run_id,
        )
        if session is None:
            logger.error(
                "[DISCOVERY] Cannot reconnect to RPi %s for HGW tunnel",
                rpi_ip,
                extra={"run_id": run_id, "rpi_ip": rpi_ip, "action": "rpi_reconnect_failed"},
            )
        return session

    # ──────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────

    def _cleanup(self, bastion_session: Optional[SSHSession]) -> None:
        logger.info("[DISCOVERY] Cleaning up sessions...", extra={"action": "cleanup"})
        try:
            if bastion_session:
                bastion_session.close()
        except Exception as e:
            logger.warning("[DISCOVERY] Error closing bastion session: %s", e)

        try:
            self.ssh_pool.close_all()
        except Exception as e:
            logger.warning("[DISCOVERY] Error closing SSH pool: %s", e)

        try:
            self.telnet_pool.close_all()
        except Exception as e:
            logger.warning("[DISCOVERY] Error closing Telnet pool: %s", e)

        logger.info("[DISCOVERY] All sessions closed.", extra={"action": "cleanup_done"})