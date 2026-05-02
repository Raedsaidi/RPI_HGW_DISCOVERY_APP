from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.switch import Switch, SwitchFact, SwitchMacEntry
from app.infrastructure.netgear_client import SwitchCollectedData


class SwitchRepository:

    def __init__(self, db: Session):
        self.db = db

    # --- CRUD ---

    def create(self, ip: str, name: Optional[str], telnet_port: int,
               telnet_user: str, telnet_pass: str) -> Switch:
        sw = Switch(
            ip=ip,
            name=name,
            telnet_port=telnet_port,
            telnet_user=telnet_user,
            telnet_pass=telnet_pass,
            created_at=datetime.utcnow(),
        )
        self.db.add(sw)
        self.db.commit()
        self.db.refresh(sw)
        return sw

    def get_by_id(self, switch_id: int) -> Optional[Switch]:
        return self.db.query(Switch).filter(Switch.id == switch_id).first()

    def get_by_ip(self, ip: str) -> Optional[Switch]:
        return self.db.query(Switch).filter(Switch.ip == ip).first()

    def list_all(self, enabled_only: bool = False) -> list[Switch]:
        q = self.db.query(Switch)
        if enabled_only:
            q = q.filter(Switch.enabled == True)
        return q.order_by(Switch.ip).all()

    def update(self, switch_id: int, **kwargs) -> Optional[Switch]:
        sw = self.get_by_id(switch_id)
        if not sw:
            return None
        for k, v in kwargs.items():
            if hasattr(sw, k) and v is not None:
                setattr(sw, k, v)
        self.db.commit()
        self.db.refresh(sw)
        return sw

    def delete(self, switch_id: int) -> bool:
        sw = self.get_by_id(switch_id)
        if not sw:
            return False
        self.db.delete(sw)
        self.db.commit()
        return True

    # --- Facts ---

    def save_fact(self, run_id: int, switch_ip: str, data: SwitchCollectedData) -> SwitchFact:
        info = data.info
        cpu = data.cpu

        # Update Switch last_seen
        sw = self.get_by_ip(switch_ip)
        if sw:
            sw.last_seen = datetime.utcnow()
            sw.mac_address = info.mac_address
            sw.firmware_version = info.firmware_version
            sw.uptime = info.uptime
            sw.serial_number = info.serial_number
            sw.model = info.model
            self.db.commit()

        fact = SwitchFact(
            run_id=run_id,
            switch_ip=switch_ip,
            collected_at=datetime.utcnow(),
            mac_address=info.mac_address,
            ip_address=info.ip_address,
            firmware_version=info.firmware_version,
            loader_version=info.loader_version,
            uptime=info.uptime,
            serial_number=info.serial_number,
            model=info.model,
            default_gateway=info.default_gateway,
            cpu_5s=cpu.cpu_5s,
            cpu_60s=cpu.cpu_60s,
            cpu_300s=cpu.cpu_300s,
            mem_free_kb=cpu.mem_free_kb,
            mem_alloc_kb=cpu.mem_alloc_kb,
            raw_show_info=data.raw_show_info,
            raw_show_cpu=data.raw_show_cpu,
            raw_show_mac=data.raw_show_mac,
        )
        self.db.add(fact)
        self.db.commit()
        return fact

    def save_mac_entry(self, run_id: int, switch_ip: str, entry) -> SwitchMacEntry:
        """Save ONE mac entry immediately (one-by-one commit)."""
        mac_entry = SwitchMacEntry(
            run_id=run_id,
            switch_ip=switch_ip,
            vid=entry.vid,
            mac=entry.mac,
            entry_type=entry.entry_type,
            port=entry.port,
            raw_line=entry.raw_line,
        )
        self.db.add(mac_entry)
        self.db.commit()
        return mac_entry

    def get_mac_entries_for_run(self, run_id: int, switch_ip: Optional[str] = None):
        q = self.db.query(SwitchMacEntry).filter(SwitchMacEntry.run_id == run_id)
        if switch_ip:
            q = q.filter(SwitchMacEntry.switch_ip == switch_ip)
        return q.all()

    def get_last_fact(self, switch_ip: str) -> Optional[SwitchFact]:
        return (
            self.db.query(SwitchFact)
            .filter(SwitchFact.switch_ip == switch_ip)
            .order_by(SwitchFact.id.desc())
            .first()
        )