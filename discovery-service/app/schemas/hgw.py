from pydantic import BaseModel, computed_field
from typing import Optional
from datetime import datetime


def _get_network_prefix(ip: Optional[str]) -> Optional[str]:
    """Extraire le préfixe réseau /24 : 192.168.1.1 → 192.168.1.x"""
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return f"{parts[0]}.{parts[1]}.{parts[2]}.x"


class HgwRead(BaseModel):
    id: int
    ip: str
    via_rpi_ip: Optional[str] = None
    via_docker_container_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    serial_number: Optional[str] = None
    software_version: Optional[str] = None
    hardware_version: Optional[str] = None
    external_ip: Optional[str] = None
    uptime_seconds: Optional[int] = None
    mem_free_kb: Optional[int] = None
    mem_total_kb: Optional[int] = None
    last_seen: Optional[datetime] = None

    # ── MODIFICATION : hgw_type supprimé ──────────────────────────────────
    # Remplacé par un champ calculé 'network' basé sur l'IP réelle.
    # ─────────────────────────────────────────────────────────────────────

    @computed_field
    @property
    def network(self) -> Optional[str]:
        """Préfixe réseau calculé dynamiquement depuis l'IP."""
        return _get_network_prefix(self.ip)

    class Config:
        from_attributes = True


class HgwListResponse(BaseModel):
    data: list[HgwRead]
    total: int
    page: int
    page_size: int
    total_pages: int