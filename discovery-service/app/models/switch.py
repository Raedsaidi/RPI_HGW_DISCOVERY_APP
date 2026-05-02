from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from app.core.db import Base


class Switch(Base):
    __tablename__ = "switches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=True)
    ip = Column(String(64), nullable=False, unique=True)
    telnet_port = Column(Integer, nullable=False, default=60000)
    telnet_user = Column(String(64), nullable=False, default="admin")
    telnet_pass = Column(String(128), nullable=False, default="password")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)

    # Last collected info
    mac_address = Column(String(32), nullable=True)
    firmware_version = Column(String(64), nullable=True)
    uptime = Column(String(128), nullable=True)
    serial_number = Column(String(64), nullable=True)
    model = Column(String(64), nullable=True)


class SwitchFact(Base):
    __tablename__ = "switch_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    switch_ip = Column(String(64), nullable=False)
    collected_at = Column(DateTime, default=datetime.utcnow)

    # show info
    mac_address = Column(String(32), nullable=True)
    ip_address = Column(String(64), nullable=True)
    firmware_version = Column(String(64), nullable=True)
    loader_version = Column(String(64), nullable=True)
    uptime = Column(String(128), nullable=True)
    serial_number = Column(String(64), nullable=True)
    model = Column(String(64), nullable=True)
    default_gateway = Column(String(64), nullable=True)

    # show cpu status
    cpu_5s = Column(String(16), nullable=True)
    cpu_60s = Column(String(16), nullable=True)
    cpu_300s = Column(String(16), nullable=True)
    mem_free_kb = Column(Integer, nullable=True)
    mem_alloc_kb = Column(Integer, nullable=True)

    # raw
    raw_show_info = Column(Text, nullable=True)
    raw_show_cpu = Column(Text, nullable=True)
    raw_show_mac = Column(Text, nullable=True)


class SwitchMacEntry(Base):
    __tablename__ = "switch_mac_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    switch_ip = Column(String(64), nullable=False)
    vid = Column(Integer, nullable=True)
    mac = Column(String(32), nullable=False)
    entry_type = Column(String(32), nullable=True)
    port = Column(String(16), nullable=True)
    raw_line = Column(Text, nullable=True)