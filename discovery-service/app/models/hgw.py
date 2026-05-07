from datetime import datetime
from sqlalchemy import BigInteger, Column, Integer, String, DateTime, Text
from app.core.db import Base


class Hgw(Base):
    __tablename__ = "hgws"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String(64), nullable=False)

    via_rpi_ip = Column(String(64), nullable=True)
    last_seen = Column(DateTime, nullable=True)

    manufacturer = Column(String(128), nullable=True)
    model_name = Column(String(64), nullable=True)
    serial_number = Column(String(128), nullable=True, unique=True)
    software_version = Column(String(64), nullable=True)
    hardware_version = Column(String(64), nullable=True)
    external_ip = Column(String(64), nullable=True)
    uptime_seconds = Column(Integer, nullable=True)
    mem_free_kb = Column(BigInteger, nullable=True)
    mem_total_kb = Column(BigInteger, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HgwFact(Base):
    __tablename__ = "hgw_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)

    # NOTE: IP HGW (souvent 192.168.x.1)
    hgw_ip = Column(String(64), nullable=False)

    # Chemin de collecte (peut être un des RPi du groupe)
    via_rpi_ip = Column(String(64), nullable=True)

    # NEW: clé d’instance HGW (MAC gateway ou fallback switch|ip)
    instance_key = Column(String(64), nullable=True)

    collected_at = Column(DateTime, default=datetime.utcnow)

    manufacturer = Column(String(128), nullable=True)
    model_name = Column(String(64), nullable=True)
    serial_number = Column(String(128), nullable=True)
    software_version = Column(String(64), nullable=True)
    hardware_version = Column(String(64), nullable=True)
    external_ip = Column(String(64), nullable=True)
    uptime_seconds = Column(Integer, nullable=True)
    mem_free_kb = Column(BigInteger, nullable=True)
    mem_total_kb = Column(BigInteger, nullable=True)
    base_mac = Column(String(32), nullable=True)
    country = Column(String(8), nullable=True)
    device_status = Column(String(32), nullable=True)

    raw_deviceinfo = Column(Text, nullable=True)
    ssh_error = Column(Text, nullable=True)