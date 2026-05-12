from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class DiscoveryRunRead(BaseModel):
    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    triggered_by: Optional[str]
    message: Optional[str]
    switches_ok: Optional[int]
    switches_err: Optional[int]
    rpis_ok: Optional[int]
    rpis_err: Optional[int]
    hgws_ok: Optional[int]
    hgws_err: Optional[int]

    class Config:
        from_attributes = True


class DeviceErrorRead(BaseModel):
    id: int
    run_id: int
    device_type: str
    device_ip: str
    stage: str
    error: str
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerResponse(BaseModel):
    run_id: int
    status: str
    message: str


# ✅ NEW
class MiniDiscoveryHgwUpdateRequest(BaseModel):
    via_rpi_ips: List[str] = []
    instance_key: Optional[str] = None
    hgw_ip: Optional[str] = None