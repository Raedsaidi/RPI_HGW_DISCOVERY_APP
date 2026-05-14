# app/repositories/rpi_docker_repo.py
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.rpi_docker import RpiDockerRun, RpiDockerContainer


class RpiDockerRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_for_rpi(
        self,
        run_id: int,
        rpi_ip_mgmt: str,
        wifi_usb_adapters: list[str],
        containers: list[dict],
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Replace snapshot for (run_id, rpi_ip_mgmt).
        """
        existing = (
            self.db.query(RpiDockerRun)
            .filter(RpiDockerRun.run_id == run_id)
            .filter(RpiDockerRun.rpi_ip_mgmt == rpi_ip_mgmt)
            .first()
        )
        if existing:
            # delete containers first
            (
                self.db.query(RpiDockerContainer)
                .filter(RpiDockerContainer.docker_run_id == existing.id)
                .delete(synchronize_session=False)
            )
            self.db.delete(existing)
            self.db.commit()

        run_row = RpiDockerRun(
            run_id=run_id,
            rpi_ip_mgmt=rpi_ip_mgmt,
            collected_at=datetime.utcnow(),
            wifi_usb_adapters=json.dumps(wifi_usb_adapters or []),
            success=bool(success),
            error=error,
        )
        self.db.add(run_row)
        self.db.flush()  # get run_row.id without committing yet

        for c in containers or []:
            row = RpiDockerContainer(
                docker_run_id=run_row.id,
                container_id=c.get("container_id"),
                name=c.get("name") or "",
                wlan_iface=c.get("wlan_iface"),
                ip=c.get("ip"),
                hgw_ip=c.get("hgw_ip"),
            )
            self.db.add(row)

        self.db.commit()

    def get_by_run_grouped(self, run_id: int) -> dict[str, dict]:
        """
        Returns:
          {
            "172.16.55.10": {
              "wifi_usb_adapters": [...],
              "docker_clients": [{name, container_id, wlan_iface, ip, hgw_ip}, ...],
              "success": bool,
              "error": str|None
            },
            ...
          }
        """
        runs = (
            self.db.query(RpiDockerRun)
            .filter(RpiDockerRun.run_id == run_id)
            .all()
        )
        if not runs:
            return {}

        run_ids = [r.id for r in runs]
        containers = (
            self.db.query(RpiDockerContainer)
            .filter(RpiDockerContainer.docker_run_id.in_(run_ids))
            .order_by(RpiDockerContainer.name.asc())
            .all()
        )

        by_run_id: dict[int, list[dict]] = {}
        for c in containers:
            by_run_id.setdefault(c.docker_run_id, []).append({
                "name": c.name,
                "container_id": c.container_id,
                "wlan_iface": c.wlan_iface,
                "ip": c.ip,
                "hgw_ip": c.hgw_ip,
            })

        out: dict[str, dict] = {}
        for r in runs:
            try:
                usb = json.loads(r.wifi_usb_adapters or "[]")
            except Exception:
                usb = []
            out[r.rpi_ip_mgmt] = {
                "wifi_usb_adapters": usb,
                "docker_clients": by_run_id.get(r.id, []),
                "success": bool(r.success),
                "error": r.error,
            }
        return out