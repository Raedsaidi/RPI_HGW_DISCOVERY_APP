from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.hgw import Hgw, HgwFact
from app.infrastructure.hgw_client import HgwCollectedData


class HgwRepository:

    def __init__(self, db: Session):
        self.db = db

    def _find_existing(self, ip: str, via_rpi_ip: Optional[str], serial_number: Optional[str]) -> Optional[Hgw]:
        if serial_number:
            hgw = self.db.query(Hgw).filter(Hgw.serial_number == serial_number).first()
            if hgw:
                return hgw

        if ip and via_rpi_ip:
            hgw = (
                self.db.query(Hgw)
                .filter(Hgw.ip == ip, Hgw.via_rpi_ip == via_rpi_ip)
                .first()
            )
            if hgw:
                return hgw

        if ip and not via_rpi_ip:
            return self.db.query(Hgw).filter(Hgw.ip == ip).first()

        return None

    def upsert(
        self,
        ip: str,
        via_rpi_ip: Optional[str] = None,
        serial_number: Optional[str] = None,
        via_docker_container_id: Optional[str] = None,
    ) -> Hgw:
        """
        Crée ou met à jour une HGW.

        La clé primaire logique est désormais le serial_number quand il est connu.
        Sinon on utilise ip + via_rpi_ip pour distinguer plusieurs HGW partageant la même IP.
        """
        hgw = self._find_existing(ip, via_rpi_ip, serial_number)
        if not hgw:
            hgw = Hgw(
                ip=ip,
                via_rpi_ip=via_rpi_ip,
                serial_number=serial_number,
                via_docker_container_id=via_docker_container_id,
                created_at=datetime.utcnow(),
            )
            self.db.add(hgw)
        else:
            if ip:
                hgw.ip = ip
            if via_rpi_ip:
                hgw.via_rpi_ip = via_rpi_ip
            if serial_number:
                hgw.serial_number = serial_number
            hgw.via_docker_container_id = via_docker_container_id

        self.db.commit()
        self.db.refresh(hgw)
        return hgw

    def update_from_fact(self, data: HgwCollectedData) -> None:
        """Met à jour les infos HGW depuis les données collectées."""
        hgw = None
        if data.serial_number:
            hgw = self.db.query(Hgw).filter(Hgw.serial_number == data.serial_number).first()

        if not hgw and data.hgw_ip and data.via_rpi_ip:
            hgw = (
                self.db.query(Hgw)
                .filter(Hgw.ip == data.hgw_ip, Hgw.via_rpi_ip == data.via_rpi_ip)
                .first()
            )

        if not hgw:
            return

        hgw.ip = data.hgw_ip or hgw.ip
        if data.via_rpi_ip:
            hgw.via_rpi_ip = data.via_rpi_ip
        hgw.via_docker_container_id = data.via_docker_container_id

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

    def get_by_identifier(self, identifier: str) -> Optional[Hgw]:
        if not identifier:
            return None

        hgw = self.db.query(Hgw).filter(Hgw.serial_number == identifier).first()
        if hgw:
            return hgw

        return self.db.query(Hgw).filter(Hgw.ip == identifier).first()

    def get_by_serial(self, serial_number: str) -> Optional[Hgw]:
        if not serial_number:
            return None
        return self.db.query(Hgw).filter(Hgw.serial_number == serial_number).first()

    def get_by_ip_and_via(self, ip: str, via_rpi_ip: str) -> Optional[Hgw]:
        return (
            self.db.query(Hgw)
            .filter(Hgw.ip == ip, Hgw.via_rpi_ip == via_rpi_ip)
            .first()
        )

    def save_fact(self, run_id: int, data: HgwCollectedData) -> HgwFact:
        fact = HgwFact(
            run_id=run_id,
            hgw_ip=data.hgw_ip,
            via_rpi_ip=data.via_rpi_ip,
            instance_key=data.instance_key,
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

        try:
            self.db.commit()
            self.db.refresh(fact)
            return fact

        except Exception as e:
            self.db.rollback()
            raise e
        
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