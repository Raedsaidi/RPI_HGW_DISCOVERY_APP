from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RpiRead(BaseModel):
    id: int
    mac: str
    ip_mgmt: str
    label: Optional[str]
    switch_ip: Optional[str]
    switch_port: Optional[str]
    hgw_ip: Optional[str]
    last_seen: Optional[datetime]
    last_ssh_success: Optional[bool]
    last_ssh_error: Optional[str]
    has_custom_credentials: bool = False

    class Config:
        from_attributes = True


class RpiCredentialSubmit(BaseModel):
    rpi_ip_mgmt: str = Field(..., example="172.16.55.25")
    ssh_user: str = Field(..., example="pi")
    ssh_pass: str = Field(..., example="mypassword")


class RpiFactRead(BaseModel):
    id: int
    run_id: int
    rpi_ip_mgmt: str
    collected_at: Optional[datetime]
    hostname: Optional[str]
    os_pretty: Optional[str]
    model: Optional[str]
    temp_celsius: Optional[str]
    mem_total_mb: Optional[int]
    mem_used_mb: Optional[int]
    mem_free_mb: Optional[int]
    disk_total_gb: Optional[str]
    disk_used_pct: Optional[str]
    docker_available: Optional[bool]
    lan_iface: Optional[str]
    lan_ip: Optional[str]
    hgw_ip: Optional[str]
    lan_mac: Optional[str]

    class Config:
        from_attributes = True