# app/services/docker_clients_sync_service.py
import logging
import time
from typing import Optional

import paramiko
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.ssh_manager import SSHPool, SSHSession
from app.infrastructure.docker_clients_collector import DockerClientsCollector
from app.parsers.piserver_parser import parse_piserver
from app.repositories.discovery_repo import DiscoveryRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.rpi_docker_repo import RpiDockerRepository
from app.models.discovery_run import PiserverSnapshot

logger = logging.getLogger(__name__)


class DockerClientsSyncService:
    """
    Sync docker client/peer container IP + container HGW + lsusb NetGear/TP-Link lines
    into rpi_docker_* tables, for a given run_id (typically latest finished run).
    """

    def __init__(self, db: Session):
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.rpi_docker_repo = RpiDockerRepository(db)
        self.ssh_pool = SSHPool()

    def _connect_bastion(self) -> tuple[bool, Optional[SSHSession], Optional[paramiko.SSHClient], str]:
        sess = SSHSession(
            host=settings.PISERVER_HOST,
            username=settings.PISERVER_USER,
            password=settings.PISERVER_PASS,
            port=22,
            tunnel=None,
            timeout=60,
        )
        ok, msg = sess.connect()
        if not ok:
            return False, None, None, msg
        return True, sess, sess._client, "OK"

    def _build_credentials_chain(self, rpi_ip: str) -> list[tuple[str, str]]:
        chain: list[tuple[str, str]] = []
        r = self.rpi_repo.get_by_ip(rpi_ip)
        if r and r.custom_ssh_user and r.custom_ssh_pass:
            chain.append((r.custom_ssh_user, r.custom_ssh_pass))

        default_creds = (settings.RPI_SSH_USER, settings.RPI_SSH_PASS)
        fallback_creds = (settings.RPI_SSH_FALLBACK_USER, settings.RPI_SSH_FALLBACK_PASS)

        if default_creds not in chain:
            chain.append(default_creds)
        if fallback_creds not in chain:
            chain.append(fallback_creds)

        return chain

    def _connect_rpi(self, rpi_ip: str, bastion_client: paramiko.SSHClient) -> tuple[Optional[SSHSession], Optional[str]]:
        for (u, p) in self._build_credentials_chain(rpi_ip):
            sess = self.ssh_pool.get_or_create(
                host=rpi_ip,
                username=u,
                password=p,
                port=22,
                tunnel=bastion_client,
                timeout=60,
            )
            if sess.connected:
                return sess, u
            ok, _ = sess.connect()
            if ok:
                return sess, u
        return None, None

    def _get_piserver_rpi_ips_for_run(self, run_id: int) -> list[str]:
        snap = (
            self.db.query(PiserverSnapshot)
            .filter(PiserverSnapshot.run_id == run_id)
            .order_by(PiserverSnapshot.id.desc())
            .first()
        )
        content = snap.content if snap else ""
        entries = parse_piserver(content) if content else []
        ips = [e.ip_mgmt for e in entries if e.ip_mgmt]
        # dedupe keep order
        seen = set()
        out = []
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                out.append(ip)
        return out

    def sync_latest_finished_run(self) -> tuple[bool, Optional[int], str]:
        """
        Sync docker data for the latest run ONLY if status is done/partial.
        """
        runs = self.discovery_repo.list_runs(skip=0, limit=1)
        if not runs:
            return False, None, "No discovery runs found"

        run = runs[0]
        if run.status == "running":
            return False, run.id, "Latest run is running (skip docker sync)"

        if run.status not in ("done", "partial"):
            return False, run.id, f"Latest run status={run.status} (skip docker sync)"

        ok, rid, msg = self.sync_for_run(run.id)
        return ok, rid, msg

    def sync_for_run(self, run_id: int) -> tuple[bool, int, str]:
        t0 = time.perf_counter()

        ok_b, bastion_sess, bastion_client, msg = self._connect_bastion()
        if not ok_b or not bastion_sess or not bastion_client:
            return False, run_id, f"Bastion SSH failed: {msg}"

        try:
            rpi_ips = self._get_piserver_rpi_ips_for_run(run_id)
            if not rpi_ips:
                return False, run_id, "No RPis found in piserver snapshot for this run"

            logger.info("[DOCKER_SYNC] run_id=%s: syncing docker clients for %d RPis", run_id, len(rpi_ips))

            for rpi_ip in rpi_ips:
                rpi_sess, user = self._connect_rpi(rpi_ip, bastion_client)
                if not rpi_sess:
                    # store failure snapshot (2.A)
                    self.rpi_docker_repo.replace_for_rpi(
                        run_id=run_id,
                        rpi_ip_mgmt=rpi_ip,
                        wifi_usb_adapters=[],
                        containers=[],
                        success=False,
                        error="SSH connection failed for RPi",
                    )
                    continue

                collector = DockerClientsCollector(rpi_sess)

                try:
                    usb_lines = collector.collect_usb_wifi_lines()
                    ok_c, containers, err = collector.collect_docker_clients()

                    if not ok_c:
                        self.rpi_docker_repo.replace_for_rpi(
                            run_id=run_id,
                            rpi_ip_mgmt=rpi_ip,
                            wifi_usb_adapters=usb_lines,
                            containers=[],
                            success=False,
                            error=err or "Docker collect failed",
                        )
                    else:
                        self.rpi_docker_repo.replace_for_rpi(
                            run_id=run_id,
                            rpi_ip_mgmt=rpi_ip,
                            wifi_usb_adapters=usb_lines,
                            containers=containers,
                            success=True,
                            error=None,
                        )

                except Exception as e:
                    self.rpi_docker_repo.replace_for_rpi(
                        run_id=run_id,
                        rpi_ip_mgmt=rpi_ip,
                        wifi_usb_adapters=[],
                        containers=[],
                        success=False,
                        error=str(e),
                    )

            elapsed = time.perf_counter() - t0
            return True, run_id, f"Docker sync done in {elapsed:.2f}s"

        finally:
            try:
                bastion_sess.close()
            except Exception:
                pass
            try:
                self.ssh_pool.close_all()
            except Exception:
                pass