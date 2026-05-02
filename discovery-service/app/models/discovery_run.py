from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.core.db import Base


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, default="running")
    # running | done | error | partial
    triggered_by = Column(String(128), nullable=True)  # username or "scheduler"
    message = Column(Text, nullable=True)

    # counters
    switches_ok = Column(Integer, default=0)
    switches_err = Column(Integer, default=0)
    rpis_ok = Column(Integer, default=0)
    rpis_err = Column(Integer, default=0)
    hgws_ok = Column(Integer, default=0)
    hgws_err = Column(Integer, default=0)


class PiserverSnapshot(Base):
    __tablename__ = "piserver_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    content = Column(Text, nullable=False)


class DeviceError(Base):
    __tablename__ = "device_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    device_type = Column(String(32), nullable=False)
    # piserver | switch | rpi | hgw
    device_ip = Column(String(64), nullable=False)
    stage = Column(String(64), nullable=False)
    error = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)