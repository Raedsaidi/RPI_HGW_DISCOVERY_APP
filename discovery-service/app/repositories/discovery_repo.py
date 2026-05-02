from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.discovery_run import DiscoveryRun, PiserverSnapshot, DeviceError


class DiscoveryRepository:

    def __init__(self, db: Session):
        self.db = db

    def create_run(self, triggered_by: str = "manual") -> DiscoveryRun:
        run = DiscoveryRun(
            started_at=datetime.utcnow(),
            status="running",
            triggered_by=triggered_by,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run(
        self,
        run_id: int,
        status: str,
        message: Optional[str] = None,
        **counters,
    ) -> None:
        run = self.db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        if run:
            run.finished_at = datetime.utcnow()
            run.status = status
            run.message = message
            for k, v in counters.items():
                if hasattr(run, k):
                    setattr(run, k, v)
            self.db.commit()

    def get_run(self, run_id: int) -> Optional[DiscoveryRun]:
        return self.db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()

    def list_runs(self, skip: int = 0, limit: int = 50) -> list[DiscoveryRun]:
        return (
            self.db.query(DiscoveryRun)
            .order_by(DiscoveryRun.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete_run(self, run_id: int) -> bool:
        run = self.db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        if not run:
            return False
        self.db.delete(run)
        self.db.commit()
        return True

    def save_piserver_snapshot(self, run_id: int, content: str) -> PiserverSnapshot:
        snap = PiserverSnapshot(
            run_id=run_id,
            collected_at=datetime.utcnow(),
            content=content,
        )
        self.db.add(snap)
        self.db.commit()
        return snap

    def save_error(
        self,
        run_id: int,
        device_type: str,
        device_ip: str,
        stage: str,
        error: str,
    ) -> DeviceError:
        err = DeviceError(
            run_id=run_id,
            device_type=device_type,
            device_ip=device_ip,
            stage=stage,
            error=error,
            created_at=datetime.utcnow(),
        )
        self.db.add(err)
        self.db.commit()
        return err

    def get_errors_for_run(self, run_id: int) -> list[DeviceError]:
        return (
            self.db.query(DeviceError)
            .filter(DeviceError.run_id == run_id)
            .order_by(DeviceError.id)
            .all()
        )