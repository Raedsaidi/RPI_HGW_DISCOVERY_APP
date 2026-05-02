from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.hgw import Hgw, HgwFact
from app.infrastructure.hgw_client import HgwCollectedData


class HgwRepository:

    def __init__(self, db: Session):
        self.db = db

    def upsert(self, ip: str, via_rpi_ip: Optional[str] = None) -> Hgw:
        """
        Crée ou met à jour une HGW.

        MODIFICATION : suppression de la logique hgw_type hardcodée.
        L'IP de la gateway vient maintenant de 'ip r s' (valeur réelle).
        """
        hgw = self.db.query(Hgw).filter(Hgw.ip == ip).first()
        if not hgw:
            hgw = Hgw(
                ip=ip,
                created_at=datetime.utcnow(),
            )
            self.db.add(hgw)

        if via_rpi_ip:
            hgw.via_rpi_ip = via_rpi_ip

        self.db.commit()
        self.db.refresh(hgw)
        return hgw

    def update_from_fact(self, ip: str, data: HgwCollectedData) -> None:
        """Met à jour les infos HGW depuis les données collectées."""
        hgw = self.db.query(Hgw).filter(Hgw.ip == ip).first()
        if not hgw:
            return

        hgw.manufacturer = data.manufacturer
        hgw.model_name = data.model_name
        hgw.serial_number = data.serial_number
        hgw.software_version = data.software_version
        hgw.hardware_version = data.hardware_version
        hgw.external_ip = data.external_ip
        hgw.uptime_seconds = data.uptime_seconds
        hgw.mem_free_kb = data.mem_free_kb
        hgw.mem_total_kb = data.mem_total_kb
        hgw.last_seen = datetime.utcnow()
        hgw.updated_at = datetime.utcnow()
        self.db.commit()

    def save_fact(self, run_id: int, data: HgwCollectedData) -> HgwFact:
        """Save HGW fact immediately (one-by-one commit)."""
        fact = HgwFact(
            run_id=run_id,
            hgw_ip=data.hgw_ip,
            via_rpi_ip=data.via_rpi_ip,
            collected_at=datetime.utcnow(),
            manufacturer=data.manufacturer,
            model_name=data.model_name,
            serial_number=data.serial_number,
            software_version=data.software_version,
            hardware_version=data.hardware_version,
            external_ip=data.external_ip,
            uptime_seconds=data.uptime_seconds,
            mem_free_kb=data.mem_free_kb,
            mem_total_kb=data.mem_total_kb,
            base_mac=data.base_mac,
            country=data.country,
            device_status=data.device_status,
            raw_deviceinfo=data.raw_deviceinfo,
            ssh_error=data.error if not data.success else None,
        )
        self.db.add(fact)
        self.db.commit()
        return fact

    def list_all(self) -> list[Hgw]:
        return self.db.query(Hgw).order_by(Hgw.ip).all()

    def get_by_ip(self, ip: str) -> Optional[Hgw]:
        return self.db.query(Hgw).filter(Hgw.ip == ip).first()

    def get_facts_for_run(self, run_id: int) -> list[HgwFact]:
        return (
            self.db.query(HgwFact)
            .filter(HgwFact.run_id == run_id)
            .all()
        )

    def get_last_fact(self, ip: str) -> Optional[HgwFact]:
        """Get the most recent fact for a HGW."""
        return (
            self.db.query(HgwFact)
            .filter(HgwFact.hgw_ip == ip)
            .order_by(HgwFact.id.desc())
            .first()
        )