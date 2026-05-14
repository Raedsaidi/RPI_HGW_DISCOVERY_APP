# app/models/rpi_docker.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from app.core.db import Base


class RpiDockerRun(Base):
    """
    One docker snapshot per (run_id, rpi_ip_mgmt).
    Stores USB wifi adapter lines + global status/error.
    """
    __tablename__ = "rpi_docker_runs"
    __table_args__ = (
        UniqueConstraint("run_id", "rpi_ip_mgmt", name="uq_rpi_docker_run_per_run_rpi"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    run_id = Column(Integer, nullable=False)
    rpi_ip_mgmt = Column(String(64), nullable=False)

    collected_at = Column(DateTime, default=datetime.utcnow)

    # JSON string: ["Bus ... NetGear ...", "Bus ... TP-Link ..."]
    wifi_usb_adapters = Column(Text, nullable=True)

    success = Column(Boolean, default=True)
    error = Column(Text, nullable=True)


class RpiDockerContainer(Base):
    """
    Containers found in a docker snapshot.
    """
    __tablename__ = "rpi_docker_containers"

    id = Column(Integer, primary_key=True, autoincrement=True)

    docker_run_id = Column(Integer, ForeignKey("rpi_docker_runs.id", ondelete="CASCADE"), nullable=False)

    container_id = Column(String(64), nullable=True)
    name = Column(String(128), nullable=False)

    wlan_iface = Column(String(32), nullable=True)
    ip = Column(String(64), nullable=True)
    hgw_ip = Column(String(64), nullable=True)