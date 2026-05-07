import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.rpi import Rpi, RpiFact, RpiCredentialOverride
from app.infrastructure.rpi_client import RpiCollectedData


class RpiRepository:

    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        mac: str,
        ip_mgmt: str,
        label: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Rpi:
        rpi = self.db.query(Rpi).filter(Rpi.mac == mac).first()
        if not rpi:
            rpi = Rpi(
                mac=mac,
                ip_mgmt=ip_mgmt,
                label=label,
                created_at=datetime.utcnow(),
            )
            self.db.add(rpi)
        else:
            rpi.ip_mgmt = ip_mgmt
            if label:
                rpi.label = label

        rpi.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(rpi)
        return rpi

    def get_by_ip(self, ip_mgmt: str) -> Optional[Rpi]:
        return self.db.query(Rpi).filter(Rpi.ip_mgmt == ip_mgmt).first()

    def get_by_mac(self, mac: str) -> Optional[Rpi]:
        return self.db.query(Rpi).filter(Rpi.mac == mac).first()

    def list_all(self) -> list[Rpi]:
        return self.db.query(Rpi).order_by(Rpi.ip_mgmt).all()

    def update_ssh_status(
        self,
        ip_mgmt: str,
        success: bool,
        error: Optional[str] = None,
        switch_ip: Optional[str] = None,
        switch_port: Optional[str] = None,
        hgw_ip: Optional[str] = None,
    ) -> None:
        rpi = self.get_by_ip(ip_mgmt)
        if rpi:
            rpi.last_ssh_success = success
            rpi.last_ssh_error = error
            rpi.last_seen = datetime.utcnow() if success else rpi.last_seen
            if switch_ip:
                rpi.switch_ip = switch_ip
            if switch_port:
                rpi.switch_port = switch_port
            if hgw_ip:
                rpi.hgw_ip = hgw_ip
            self.db.commit()

    def save_fact(
        self,
        run_id: int,
        rpi_mac: Optional[str],
        data: RpiCollectedData,
    ) -> RpiFact:
        """Save RPi fact immediately after collection (one-by-one)."""
        fact = RpiFact(
            run_id=run_id,
            rpi_mac=rpi_mac,
            rpi_ip_mgmt=data.ip_mgmt,
            collected_at=datetime.utcnow(),
            # Identity
            hostname=data.hostname,
            os_name=data.os_name,
            os_version=data.os_version,
            os_pretty=data.os_pretty,
            model=data.model,
            kernel=data.kernel,
            # Network
            lan_iface=data.lan_iface,
            lan_ip=data.lan_ip,
            lan_mac=data.lan_mac,
            hgw_ip=data.hgw_ip,

            # NEW
            hgw_gateway_mac=getattr(data, "hgw_gateway_mac", None),

            all_ips=data.all_ips,
            # Metrics
            temp_celsius=data.temp_celsius,
            mem_total_mb=data.mem_total_mb,
            mem_used_mb=data.mem_used_mb,
            mem_free_mb=data.mem_free_mb,
            disk_total_gb=data.disk_total,
            disk_used_gb=data.disk_used,
            disk_used_pct=data.disk_used_pct,
            # Processes
            running_scripts=data.running_scripts,
            running_python=data.running_python,
            docker_available=data.docker_available,
            docker_containers=data.docker_containers,
            docker_images=data.docker_images,
            # USB
            usb_devices=data.usb_devices,
            # Raw
            raw_ip_addr=data.raw_ip_addr,
            raw_ps=data.raw_ps,
        )
        self.db.add(fact)
        self.db.commit()
        return fact

    def get_last_fact(self, ip_mgmt: str) -> Optional[RpiFact]:
        return (
            self.db.query(RpiFact)
            .filter(RpiFact.rpi_ip_mgmt == ip_mgmt)
            .order_by(RpiFact.id.desc())
            .first()
        )

    def get_facts_for_run(self, run_id: int) -> list[RpiFact]:
        return (
            self.db.query(RpiFact)
            .filter(RpiFact.run_id == run_id)
            .all()
        )

    # ── Credential overrides ──────────────────────────────────────────────

    def save_credential_override(
        self,
        ip_mgmt: str,
        ssh_user: str,
        ssh_pass: str,
        submitted_by: str,
    ) -> RpiCredentialOverride:
        override = (
            self.db.query(RpiCredentialOverride)
            .filter(RpiCredentialOverride.rpi_ip_mgmt == ip_mgmt)
            .first()
        )
        if not override:
            override = RpiCredentialOverride(
                rpi_ip_mgmt=ip_mgmt,
                created_at=datetime.utcnow(),
            )
            self.db.add(override)

        override.ssh_user = ssh_user
        override.ssh_pass = ssh_pass
        override.submitted_by = submitted_by
        override.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(override)

        # Also update the Rpi table
        rpi = self.get_by_ip(ip_mgmt)
        if rpi:
            rpi.custom_ssh_user = ssh_user
            rpi.custom_ssh_pass = ssh_pass
            self.db.commit()

        return override

    def get_credential_override(
        self, ip_mgmt: str
    ) -> Optional[RpiCredentialOverride]:
        return (
            self.db.query(RpiCredentialOverride)
            .filter(RpiCredentialOverride.rpi_ip_mgmt == ip_mgmt)
            .first()
        )