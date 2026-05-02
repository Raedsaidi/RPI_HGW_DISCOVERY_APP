from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from app.core.db import Base


class Rpi(Base):
    __tablename__ = "rpis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac = Column(String(32), nullable=False, unique=True)
    ip_mgmt = Column(String(64), nullable=False)
    label = Column(String(128), nullable=True)

    # Custom credentials (if different from default)
    custom_ssh_user = Column(String(64), nullable=True)
    custom_ssh_pass = Column(String(128), nullable=True)

    # Last known state
    switch_ip = Column(String(64), nullable=True)
    switch_port = Column(String(16), nullable=True)
    hgw_ip = Column(String(64), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    last_ssh_success = Column(Boolean, default=False)
    last_ssh_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RpiFact(Base):
    __tablename__ = "rpi_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    rpi_mac = Column(String(32), nullable=True)
    rpi_ip_mgmt = Column(String(64), nullable=False)
    collected_at = Column(DateTime, default=datetime.utcnow)

    # Identity
    hostname = Column(String(128), nullable=True)
    os_name = Column(String(128), nullable=True)
    os_version = Column(String(64), nullable=True)
    os_pretty = Column(String(256), nullable=True)
    model = Column(String(128), nullable=True)
    kernel = Column(String(256), nullable=True)

    # Network
    lan_iface = Column(String(32), nullable=True)
    lan_ip = Column(String(64), nullable=True)
    lan_mac = Column(String(32), nullable=True)       # ← NOUVEAU
    hgw_ip = Column(String(64), nullable=True)
    all_ips = Column(MEDIUMTEXT, nullable=True)

    # Metrics
    temp_celsius = Column(String(16), nullable=True)
    mem_total_mb = Column(Integer, nullable=True)
    mem_used_mb = Column(Integer, nullable=True)
    mem_free_mb = Column(Integer, nullable=True)
    disk_total_gb = Column(String(32), nullable=True)
    disk_used_gb = Column(String(32), nullable=True)
    disk_used_pct = Column(String(8), nullable=True)

    # Running scripts
    running_scripts = Column(MEDIUMTEXT, nullable=True)
    running_python = Column(Text, nullable=True)
    docker_available = Column(Boolean, default=False)
    docker_containers = Column(Text, nullable=True)
    docker_images = Column(MEDIUMTEXT, nullable=True)

    # USB
    usb_devices = Column(MEDIUMTEXT, nullable=True)

    # Raw
    raw_ip_addr = Column(MEDIUMTEXT, nullable=True)   # ← REMPLACE raw_ifconfig
    raw_ps = Column(MEDIUMTEXT, nullable=True)


class RpiCredentialOverride(Base):
    """Allows frontend to submit custom credentials for failed RPis."""
    __tablename__ = "rpi_credential_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rpi_ip_mgmt = Column(String(64), nullable=False, unique=True)
    ssh_user = Column(String(64), nullable=False)
    ssh_pass = Column(String(128), nullable=False)
    submitted_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)