# discovery-service/app/services/discovery_service.py
import ipaddress
import ipaddress
import json
import logging
import time
from datetime import datetime
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
from app.infrastructure.hgw_client import HgwClient       # ← import unique ici
from app.infrastructure.netgear_client import NetgearClient  # ← import unique ici
from app.infrastructure.rpi_client import RpiClient
from app.infrastructure.ssh_manager import SSHPool, SSHSession
from app.infrastructure.telnet_manager import TelnetPool
from app.parsers.piserver_parser import parse_piserver
from app.repositories.discovery_repo import DiscoveryRepository
from app.repositories.hgw_repo import HgwRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.switch_repo import SwitchRepository

logger = get_logger(__name__)


class DiscoveryService:
    """
    Orchestrates the full network discovery process:
      1. Connect to bastion (piserver)
      2. Read & parse /etc/dnsmasq.d/piserver
      3. Collect switch facts + MAC tables
      4. SSH to each RPi (with credential fallback) → collect metrics
      5. SSH to each HGW through RPi tunnel → collect DeviceInfo
    """

    def __init__(self, db: Session):
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.switch_repo    = SwitchRepository(db)
        self.rpi_repo       = RpiRepository(db)
        self.hgw_repo       = HgwRepository(db)
        self.ssh_pool       = SSHPool()
        self.telnet_pool    = TelnetPool()

    # ──────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
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
            "switches_ok":  0,
            "switches_err": 0,
            "rpis_ok":      0,
            "rpis_err":     0,
            "hgws_ok":      0,
            "hgws_err":     0,
        }

        bastion_session: Optional[SSHSession] = None
        bastion_client: Optional[paramiko.SSHClient] = None

        try:
            # ══════════════════════════════════════════════════
            # STEP 1: Connect to Bastion
            # ══════════════════════════════════════════════════
            bastion_session, bastion_client = self._connect_bastion(run_id)
            if bastion_session is None:
                total_elapsed = time.perf_counter() - run_start
                log_sync_end(logger, run_id, "error", total_elapsed, counters)
                return run_id

            # ══════════════════════════════════════════════════
            # STEP 2: Read piserver file
            # ══════════════════════════════════════════════════
            piserver_mac_to_ip = self._read_piserver(run_id, bastion_session)
            if piserver_mac_to_ip is None:
                total_elapsed = time.perf_counter() - run_start
                log_sync_end(logger, run_id, "error", total_elapsed, counters)
                return run_id

            piserver_macs = set(piserver_mac_to_ip.keys())

            # ══════════════════════════════════════════════════
            # STEP 3: Process each switch
            # ══════════════════════════════════════════════════
            rpi_to_switch = self._process_switches(
                run_id=run_id,
                bastion_client=bastion_client,
                piserver_macs=piserver_macs,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

            # ══════════════════════════════════════════════════
            # STEP 4 & 5: Process each RPi
            # ══════════════════════════════════════════════════
            hgw_targets = self._process_rpis(
                run_id=run_id,
                bastion_client=bastion_client,
                rpi_to_switch=rpi_to_switch,
                piserver_mac_to_ip=piserver_mac_to_ip,
                counters=counters,
            )

            # ══════════════════════════════════════════════════
            # STEP 6: Process each HGW
            # ══════════════════════════════════════════════════
            self._process_hgws(
                run_id=run_id,
                bastion_client=bastion_client,
                hgw_targets=hgw_targets,
                counters=counters,
            )

        except Exception as e:
            logger.error(
                "[DISCOVERY] Unexpected error in run #%d: %s",
                run_id, e,
                exc_info=True,
                extra={"run_id": run_id, "action": "discovery_fatal_error"},
            )
            self.discovery_repo.save_error(
                run_id, "discovery", "global", "fatal", str(e)
            )

        finally:
            self._cleanup(bastion_session)

        # ── Finish run ────────────────────────────────────────
        total_elapsed = time.perf_counter() - run_start
        total_errors = (
            counters["switches_err"]
            + counters["rpis_err"]
            + counters["hgws_err"]
        )
        status = "done" if total_errors == 0 else "partial"
        msg = (
            None
            if total_errors == 0
            else (
                f"Completed with errors: "
                f"sw_err={counters['switches_err']}, "
                f"rpi_err={counters['rpis_err']}, "
                f"hgw_err={counters['hgws_err']}"
            )
        )

        self.discovery_repo.finish_run(
            run_id,
            status=status,
            message=msg,
            **counters,
        )

        log_sync_end(logger, run_id, status, total_elapsed, counters)
        return run_id

    # ──────────────────────────────────────────────────────────
    # STEP 1: BASTION CONNECTION
    # ──────────────────────────────────────────────────────────

    def _connect_bastion(
        self, run_id: int
    ) -> tuple[Optional[SSHSession], Optional[paramiko.SSHClient]]:
        """Connect to the bastion SSH server."""
        logger.info(
            "[DISCOVERY] Connecting to bastion %s (user=%s)",
            settings.PISERVER_HOST,
            settings.PISERVER_USER,
            extra={
                "run_id":    run_id,
                "device_ip": settings.PISERVER_HOST,
                "action":    "bastion_connect",
            },
        )
        start = time.perf_counter()

        bastion_session = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=15,
        )
        ok, msg   = bastion_session.connect()
        elapsed   = time.perf_counter() - start

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
                "[DISCOVERY] ✗ Bastion connection failed: %s", msg,
                extra={"run_id": run_id, "action": "bastion_connect_failed"},
            )
            self.discovery_repo.save_error(
                run_id, "piserver", settings.PISERVER_HOST, "ssh", msg
            )
            self.discovery_repo.finish_run(
                run_id, status="error", message=f"Bastion SSH failed: {msg}"
            )
            return None, None

        bastion_client = bastion_session._client
        return bastion_session, bastion_client

    # ──────────────────────────────────────────────────────────
    # STEP 2: READ PISERVER FILE
    # ──────────────────────────────────────────────────────────

    def _read_piserver(
        self,
        run_id: int,
        bastion_session: SSHSession,
    ) -> Optional[dict]:
        """
        Read and parse /etc/dnsmasq.d/piserver.
        Returns {mac: ip_mgmt} dict or None on failure.
        """
        logger.info(
            "[DISCOVERY] Reading piserver file: %s",
            settings.PISERVER_FILE,
            extra={
                "run_id":    run_id,
                "action":    "read_piserver",
                "device_ip": settings.PISERVER_HOST,
            },
        )
        start = time.perf_counter()

        ok, content = bastion_session.execute(
            f"cat {settings.PISERVER_FILE}", timeout=15
        )
        elapsed = time.perf_counter() - start

        if not ok or not content.strip():
            logger.error(
                "[DISCOVERY] ✗ Failed to read piserver file (%.2fs): %s",
                elapsed, content,
                extra={"run_id": run_id, "action": "read_piserver_failed"},
            )
            self.discovery_repo.save_error(
                run_id,
                "piserver",
                settings.PISERVER_HOST,
                "read_file",
                content or "Empty response",
            )
            self.discovery_repo.finish_run(
                run_id, status="error", message="Cannot read piserver file"
            )
            return None

        # Save snapshot
        self.discovery_repo.save_piserver_snapshot(run_id, content)

        # Parse entries
        rpi_entries = parse_piserver(content)

        # Upsert all RPis into DB
        for entry in rpi_entries:
            self.rpi_repo.upsert(
                entry.mac, entry.ip_mgmt, entry.label, entry.group
            )

        mac_to_ip = {e.mac: e.ip_mgmt for e in rpi_entries}

        logger.info(
            "[DISCOVERY] ✓ Piserver parsed: %d active RPi entries (%.2fs)",
            len(rpi_entries),
            elapsed,
            extra={
                "run_id":    run_id,
                "action":    "piserver_parsed",
                "rpi_count": len(rpi_entries),
                "elapsed_s": round(elapsed, 3),
            },
        )
        return mac_to_ip

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
        """
        Connect to each switch via Telnet through bastion.
        Collect facts + MAC table.
        Returns: {rpi_ip: (switch_ip, port)}
        """
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
            extra={
                "run_id": run_id,
                "action": "switches_start",
                "count":  len(switches),
            },
        )

        rpi_to_switch: dict[str, tuple[str, str]] = {}

        for sw in switches:
            sw_start = time.perf_counter()
            logger.info(
                "[DISCOVERY] ─── Switch %s (%s) ───",
                sw.ip, sw.name or "unnamed",
                extra={
                    "run_id":    run_id,
                    "switch_ip": sw.ip,
                    "action":    "switch_start",
                },
            )

            try:
                telnet_sess = self.telnet_pool.get_or_create(
                    switch_ip=sw.ip,
                    switch_port=sw.telnet_port,
                    username=sw.telnet_user,
                    password=sw.telnet_pass,
                    bastion_client=bastion_client,
                    timeout=20,
                )

                if not telnet_sess.connected:
                    ok_conn, conn_msg = telnet_sess.connect()
                    if not ok_conn:
                        raise ConnectionError(
                            f"Telnet connection failed: {conn_msg}"
                        )

                logger.info(
                    "[DISCOVERY] Telnet connected to switch %s", sw.ip,
                    extra={
                        "run_id":    run_id,
                        "switch_ip": sw.ip,
                        "action":    "switch_telnet_ok",
                    },
                )

                client = NetgearClient(telnet_sess)
                data   = client.collect_all()

                if not data.success:
                    raise Exception(data.error or "collect_all() failed")

                logger.info(
                    "[DISCOVERY] Switch %s: firmware=%s, model=%s, uptime=%s",
                    sw.ip,
                    data.info.firmware_version,
                    data.info.model,
                    data.info.uptime,
                    extra={
                        "run_id":    run_id,
                        "switch_ip": sw.ip,
                        "action":    "switch_info",
                        "firmware":  data.info.firmware_version,
                        "model":     data.info.model,
                    },
                )

                self.switch_repo.save_fact(run_id, sw.ip, data)

                # ── Filter MAC entries to ignore management port ──
                filtered_mac_entries = [
                    entry for entry in data.mac_entries 
                    if sw.port_management is None or entry.port != sw.port_management
                ]

                if len(filtered_mac_entries) != len(data.mac_entries):
                    logger.info(
                        "[DISCOVERY] Switch %s: filtered %d management port entries (port=%s)",
                        sw.ip, len(data.mac_entries) - len(filtered_mac_entries), sw.port_management,
                        extra={
                            "run_id": run_id,
                            "switch_ip": sw.ip,
                            "action": "switch_mac_filtered",
                            "total_macs": len(data.mac_entries),
                            "filtered_macs": len(filtered_mac_entries),
                            "management_port": sw.port_management,
                        },
                    )

                rpi_count_on_switch = 0
                for entry in filtered_mac_entries:
                    self.switch_repo.save_mac_entry(run_id, sw.ip, entry)

                    mac_upper = entry.mac.upper()
                    if mac_upper in piserver_macs:
                        rpi_ip = piserver_mac_to_ip[mac_upper]
                        rpi_to_switch[rpi_ip] = (sw.ip, entry.port)
                        rpi_count_on_switch  += 1
                        logger.debug(
                            "[DISCOVERY] RPi %s found on switch %s port %s (MAC=%s)",
                            rpi_ip, sw.ip, entry.port, mac_upper,
                            extra={
                                "run_id":    run_id,
                                "switch_ip": sw.ip,
                                "rpi_ip":    rpi_ip,
                                "port":      entry.port,
                                "mac":       mac_upper,
                            },
                        )

                sw_elapsed = time.perf_counter() - sw_start
                log_switch_collect(
                    logger,
                    switch_ip=sw.ip,
                    run_id=run_id,
                    mac_count=len(filtered_mac_entries),  # Use filtered count
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
                self.discovery_repo.save_error(
                    run_id, "switch", sw.ip, "collect", str(e)
                )
                counters["switches_err"] += 1
                continue

        logger.info(
            "[DISCOVERY] Switches done: ok=%d err=%d, %d RPis identified",
            counters["switches_ok"],
            counters["switches_err"],
            len(rpi_to_switch),
            extra={
                "run_id":          run_id,
                "action":          "switches_done",
                "rpi_identified":  len(rpi_to_switch),
            },
        )
        return rpi_to_switch

    # ──────────────────────────────────────────────────────────
    # STEP 4 & 5: PROCESS RPIs
    # ──────────────────────────────────────────────────────────

    def _process_rpis(
        self,
        run_id: int,
        bastion_client: paramiko.SSHClient,
        rpi_to_switch: dict,
        piserver_mac_to_ip: dict,
        counters: dict,
    ) -> dict:
        """
        SSH to each RPi through bastion (with credential fallback).
        Collect metrics, OS info, network interfaces.
        Returns: {hgw_ip: via_rpi_ip}
        """
        rpi_ips = sorted(rpi_to_switch.keys(), key=ipaddress.ip_address)

        if not rpi_ips:
            logger.warning(
                "[DISCOVERY] No RPis found on any switch for run #%d",
                run_id,
                extra={"run_id": run_id, "action": "no_rpis_found"},
            )
            return {}

        logger.info(
            "[DISCOVERY] Processing %d RPis",
            len(rpi_ips),
            extra={
                "run_id": run_id,
                "action": "rpis_start",
                "count":  len(rpi_ips),
            },
        )

        hgw_targets: dict[str, str] = {}
        ip_to_mac = {ip: mac for mac, ip in piserver_mac_to_ip.items()}

        for rpi_ip in rpi_ips:
            switch_ip, switch_port = rpi_to_switch[rpi_ip]
            rpi_mac   = ip_to_mac.get(rpi_ip)
            rpi_start = time.perf_counter()

            logger.info(
                "[DISCOVERY] ─── RPi %s (switch=%s port=%s) ───",
                rpi_ip, switch_ip, switch_port,
                extra={
                    "run_id":    run_id,
                    "rpi_ip":    rpi_ip,
                    "switch_ip": switch_ip,
                    "action":    "rpi_start",
                },
            )

            try:
                # ── Connexion avec fallback credentials ───────
                rpi_session, used_user = self._connect_rpi_with_fallback(
                    rpi_ip=rpi_ip,
                    bastion_client=bastion_client,
                    run_id=run_id,
                )

                if rpi_session is None:
                    raise ConnectionError(
                        f"All SSH credentials failed for {rpi_ip}"
                    )

                # ── Collect RPi data ───────────────────────────
                rpi_client = RpiClient(rpi_session)
                collected  = rpi_client.collect_all(rpi_ip)

                logger.debug(
                    "[DISCOVERY] RPi %s collected: hostname=%s, os=%s, "
                    "model=%s, temp=%s°C, mem=%s/%sMB, hgw=%s",
                    rpi_ip,
                    collected.hostname,
                    collected.os_pretty,
                    collected.model,
                    collected.temp_celsius,
                    collected.mem_used_mb,
                    collected.mem_total_mb,
                    collected.hgw_ip,
                    extra={
                        "run_id":   run_id,
                        "rpi_ip":   rpi_ip,
                        "hostname": collected.hostname,
                        "hgw_ip":   collected.hgw_ip,
                        "temp":     collected.temp_celsius,
                    },
                )

                # ── Log running scripts ────────────────────────
                try:
                    scripts      = json.loads(collected.running_scripts or "[]")
                    python_procs = json.loads(collected.running_python or "[]")
                    if scripts or python_procs:
                        logger.info(
                            "[DISCOVERY] RPi %s running: scripts=%s python=%s",
                            rpi_ip, scripts, python_procs,
                            extra={
                                "run_id":          run_id,
                                "rpi_ip":          rpi_ip,
                                "running_scripts": scripts,
                                "running_python":  python_procs,
                                "action":          "rpi_processes",
                            },
                        )
                except Exception:
                    pass

                # ── Log docker ────────────────────────────────
                if collected.docker_available:
                    try:
                        containers = json.loads(
                            collected.docker_containers or "[]"
                        )
                        logger.info(
                            "[DISCOVERY] RPi %s docker: %d containers",
                            rpi_ip, len(containers),
                            extra={
                                "run_id":            run_id,
                                "rpi_ip":            rpi_ip,
                                "docker_containers": len(containers),
                                "action":            "rpi_docker",
                            },
                        )
                    except Exception:
                        pass

                # ── Save fact ─────────────────────────────────
                self.rpi_repo.save_fact(run_id, rpi_mac, collected)

                # ── Update RPi status ─────────────────────────
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

                # ── Queue HGW for collection ───────────────────
                if collected.hgw_ip:
                    if collected.hgw_ip not in hgw_targets:
                        hgw_targets[collected.hgw_ip] = rpi_ip
                        logger.debug(
                            "[DISCOVERY] HGW %s queued via RPi %s",
                            collected.hgw_ip, rpi_ip,
                            extra={
                                "run_id": run_id,
                                "hgw_ip": collected.hgw_ip,
                                "rpi_ip": rpi_ip,
                            },
                        )
                    self.hgw_repo.upsert(collected.hgw_ip, via_rpi_ip=rpi_ip)

            except ConnectionError as e:
                rpi_elapsed = time.perf_counter() - rpi_start
                logger.warning(
                    "[DISCOVERY] RPi %s SSH connection failed (%.2fs): %s",
                    rpi_ip, rpi_elapsed, e,
                    extra={
                        "run_id":    run_id,
                        "rpi_ip":    rpi_ip,
                        "action":    "rpi_ssh_failed",
                        "elapsed_s": round(rpi_elapsed, 3),
                    },
                )
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
                self.discovery_repo.save_error(
                    run_id, "rpi", rpi_ip, "ssh", str(e)
                )
                self.rpi_repo.update_ssh_status(
                    rpi_ip, success=False, error=str(e)
                )
                counters["rpis_err"] += 1

            except Exception as e:
                rpi_elapsed = time.perf_counter() - rpi_start
                logger.error(
                    "[DISCOVERY] RPi %s collection failed (%.2fs): %s",
                    rpi_ip, rpi_elapsed, e,
                    exc_info=True,
                    extra={
                        "run_id":    run_id,
                        "rpi_ip":    rpi_ip,
                        "action":    "rpi_collect_failed",
                        "elapsed_s": round(rpi_elapsed, 3),
                    },
                )
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
                self.discovery_repo.save_error(
                    run_id, "rpi", rpi_ip, "collect", str(e)
                )
                self.rpi_repo.update_ssh_status(
                    rpi_ip, success=False, error=str(e)
                )
                counters["rpis_err"] += 1

        logger.info(
            "[DISCOVERY] RPis done: ok=%d err=%d, %d HGWs queued",
            counters["rpis_ok"],
            counters["rpis_err"],
            len(hgw_targets),
            extra={
                "run_id":       run_id,
                "action":       "rpis_done",
                "hgws_queued":  len(hgw_targets),
            },
        )
        return hgw_targets

    # ──────────────────────────────────────────────────────────
    # STEP 6: PROCESS HGWs
    # ──────────────────────────────────────────────────────────

    def _process_hgws(
        self,
        run_id: int,
        bastion_client: paramiko.SSHClient,
        hgw_targets: dict,
        counters: dict,
    ) -> None:
        """
        SSH to each HGW through the RPi as a jump host.
        Collect DeviceInfo via ba-cli.
        """
        if not hgw_targets:
            logger.info(
                "[DISCOVERY] No HGWs to process for run #%d",
                run_id,
                extra={"run_id": run_id, "action": "no_hgws"},
            )
            return

        logger.info(
            "[DISCOVERY] Processing %d HGWs",
            len(hgw_targets),
            extra={
                "run_id": run_id,
                "action": "hgws_start",
                "count":  len(hgw_targets),
            },
        )

        for hgw_ip, via_rpi_ip in hgw_targets.items():
            hgw_start = time.perf_counter()

            logger.info(
                "[DISCOVERY] ─── HGW %s (via RPi %s) ───",
                hgw_ip, via_rpi_ip,
                extra={
                    "run_id": run_id,
                    "hgw_ip": hgw_ip,
                    "rpi_ip": via_rpi_ip,
                    "action": "hgw_start",
                },
            )

            try:
                # ── Get RPi session ────────────────────────────
                rpi_session = self._get_rpi_session(
                    via_rpi_ip, bastion_client, run_id
                )
                if rpi_session is None:
                    raise ConnectionError(
                        f"Cannot get RPi session for {via_rpi_ip}"
                    )

                rpi_client_obj = rpi_session._client

                # ── Connect to HGW through RPi tunnel ─────────
                logger.debug(
                    "[DISCOVERY] Opening SSH tunnel: bastion→RPi(%s)→HGW(%s)",
                    via_rpi_ip, hgw_ip,
                    extra={
                        "run_id": run_id,
                        "hgw_ip": hgw_ip,
                        "rpi_ip": via_rpi_ip,
                        "action": "hgw_tunnel",
                    },
                )

                hgw_session = self.ssh_pool.get_or_create(
                    host=hgw_ip,
                    username=settings.HGW_SSH_USER,
                    password=settings.HGW_SSH_PASS,
                    port=22,
                    tunnel=rpi_client_obj,
                    timeout=20,
                )

                if not hgw_session.connected:
                    connect_start   = time.perf_counter()
                    ok_h, err_h     = hgw_session.connect()
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
                        raise ConnectionError(f"HGW SSH failed: {err_h}")

                # ── Collect HGW DeviceInfo ─────────────────────
                hgw_client = HgwClient(hgw_session)
                hgw_data   = hgw_client.collect_deviceinfo(hgw_ip, via_rpi_ip)

                # ── Save HGW fact ──────────────────────────────
                self.hgw_repo.save_fact(run_id, hgw_data)

                hgw_elapsed = time.perf_counter() - hgw_start

                if hgw_data.success:
                    self.hgw_repo.update_from_fact(hgw_ip, hgw_data)
                    log_hgw_collect(
                        logger,
                        hgw_ip=hgw_ip,
                        via_rpi=via_rpi_ip,
                        run_id=run_id,
                        model=hgw_data.model_name,
                        elapsed_s=hgw_elapsed,
                        success=True,
                    )
                    counters["hgws_ok"] += 1
                else:
                    log_hgw_collect(
                        logger,
                        hgw_ip=hgw_ip,
                        via_rpi=via_rpi_ip,
                        run_id=run_id,
                        model=None,
                        elapsed_s=hgw_elapsed,
                        success=False,
                        error=hgw_data.error,
                    )
                    self.discovery_repo.save_error(
                        run_id,
                        "hgw",
                        hgw_ip,
                        "ba_cli",
                        hgw_data.error or "ba-cli returned no data",
                    )
                    counters["hgws_err"] += 1

            except ConnectionError as e:
                hgw_elapsed = time.perf_counter() - hgw_start
                logger.warning(
                    "[DISCOVERY] HGW %s SSH connection failed (%.2fs): %s",
                    hgw_ip, hgw_elapsed, e,
                    extra={
                        "run_id":    run_id,
                        "hgw_ip":    hgw_ip,
                        "rpi_ip":    via_rpi_ip,
                        "action":    "hgw_ssh_failed",
                        "elapsed_s": round(hgw_elapsed, 3),
                    },
                )
                log_hgw_collect(
                    logger,
                    hgw_ip=hgw_ip,
                    via_rpi=via_rpi_ip,
                    run_id=run_id,
                    model=None,
                    elapsed_s=hgw_elapsed,
                    success=False,
                    error=str(e),
                )
                self.discovery_repo.save_error(
                    run_id, "hgw", hgw_ip, "ssh", str(e)
                )
                counters["hgws_err"] += 1

            except Exception as e:
                hgw_elapsed = time.perf_counter() - hgw_start
                logger.error(
                    "[DISCOVERY] HGW %s collection failed (%.2fs): %s",
                    hgw_ip, hgw_elapsed, e,
                    exc_info=True,
                    extra={
                        "run_id":    run_id,
                        "hgw_ip":    hgw_ip,
                        "rpi_ip":    via_rpi_ip,
                        "action":    "hgw_collect_failed",
                        "elapsed_s": round(hgw_elapsed, 3),
                    },
                )
                log_hgw_collect(
                    logger,
                    hgw_ip=hgw_ip,
                    via_rpi=via_rpi_ip,
                    run_id=run_id,
                    model=None,
                    elapsed_s=hgw_elapsed,
                    success=False,
                    error=str(e),
                )
                self.discovery_repo.save_error(
                    run_id, "hgw", hgw_ip, "collect", str(e)
                )
                counters["hgws_err"] += 1

        logger.info(
            "[DISCOVERY] HGWs done: ok=%d err=%d",
            counters["hgws_ok"],
            counters["hgws_err"],
            extra={"run_id": run_id, "action": "hgws_done"},
        )

    # ──────────────────────────────────────────────────────────
    # HELPERS — CREDENTIALS & SSH
    # ──────────────────────────────────────────────────────────

    def _build_credentials_chain(self, rpi_ip: str) -> list[tuple[str, str]]:
        """
        Construire la chaîne de credentials à essayer dans l'ordre :
          1. Custom credentials (si définis en DB pour ce RPi)
          2. Default  : pi / raspberry
          3. Fallback : root / sah
        """
        chain: list[tuple[str, str]] = []

        rpi_db = self.rpi_repo.get_by_ip(rpi_ip)
        if rpi_db and rpi_db.custom_ssh_user and rpi_db.custom_ssh_pass:
            chain.append((rpi_db.custom_ssh_user, rpi_db.custom_ssh_pass))

        default_creds  = (settings.RPI_SSH_USER, settings.RPI_SSH_PASS)
        fallback_creds = (
            settings.RPI_SSH_FALLBACK_USER,
            settings.RPI_SSH_FALLBACK_PASS,
        )

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
        """
        Tente de se connecter au RPi en essayant chaque credential.
        Returns: (session, username) ou (None, None)
        """
        credentials_chain = self._build_credentials_chain(rpi_ip)

        for attempt, (ssh_user, ssh_pass) in enumerate(
            credentials_chain, start=1
        ):
            rpi_session = self.ssh_pool.get_or_create(
                host=rpi_ip,
                username=ssh_user,
                password=ssh_pass,
                port=22,
                tunnel=bastion_client,
                timeout=15,
            )

            if rpi_session.connected:
                return rpi_session, ssh_user

            connect_start   = time.perf_counter()
            ok, err_msg     = rpi_session.connect()
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
                    "[DISCOVERY] ✓ RPi %s connected with user=%s "
                    "(attempt %d/%d, %.2fs)",
                    rpi_ip, ssh_user, attempt,
                    len(credentials_chain), connect_elapsed,
                    extra={
                        "run_id":    run_id,
                        "rpi_ip":    rpi_ip,
                        "ssh_user":  ssh_user,
                        "attempt":   attempt,
                        "action":    "rpi_ssh_ok",
                    },
                )
                return rpi_session, ssh_user

            logger.warning(
                "[DISCOVERY] ✗ RPi %s SSH failed with user=%s "
                "(attempt %d/%d): %s",
                rpi_ip, ssh_user, attempt,
                len(credentials_chain), err_msg,
                extra={
                    "run_id":   run_id,
                    "rpi_ip":   rpi_ip,
                    "ssh_user": ssh_user,
                    "attempt":  attempt,
                    "action":   "rpi_ssh_attempt_failed",
                },
            )

        logger.error(
            "[DISCOVERY] ✗ RPi %s — All %d SSH credential attempts failed",
            rpi_ip, len(credentials_chain),
            extra={
                "run_id":   run_id,
                "rpi_ip":   rpi_ip,
                "action":   "rpi_all_credentials_failed",
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
        """Récupère ou reconnecte la session RPi pour le tunnel HGW."""
        session, _ = self._connect_rpi_with_fallback(
            rpi_ip=rpi_ip,
            bastion_client=bastion_client,
            run_id=run_id,
        )

        if session is None:
            logger.error(
                "[DISCOVERY] Cannot reconnect to RPi %s for HGW tunnel",
                rpi_ip,
                extra={
                    "run_id": run_id,
                    "rpi_ip": rpi_ip,
                    "action": "rpi_reconnect_failed",
                },
            )
        return session

    # ──────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────

    def _cleanup(self, bastion_session: Optional[SSHSession]) -> None:
        """Close all SSH and Telnet sessions."""
        logger.info(
            "[DISCOVERY] Cleaning up sessions...",
            extra={"action": "cleanup"},
        )
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

        logger.info(
            "[DISCOVERY] All sessions closed.",
            extra={"action": "cleanup_done"},
        )