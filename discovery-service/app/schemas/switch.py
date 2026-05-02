from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SwitchCreate(BaseModel):
    ip: str = Field(..., example="172.16.55.238")
    name: Optional[str] = Field(None, example="Switch 1 - Floor 2")
    telnet_port: int = Field(default=60000)
    telnet_user: str = Field(default="admin")
    telnet_pass: str = Field(default="password")
    enabled: bool = Field(default=True)


class SwitchUpdate(BaseModel):
    name: Optional[str] = None
    telnet_port: Optional[int] = None
    telnet_user: Optional[str] = None
    telnet_pass: Optional[str] = None
    enabled: Optional[bool] = None


class SwitchRead(BaseModel):
    id: int
    ip: str
    name: Optional[str]
    telnet_port: int
    telnet_user: str
    enabled: bool
    mac_address: Optional[str]
    firmware_version: Optional[str]
    uptime: Optional[str]
    serial_number: Optional[str]
    model: Optional[str]
    last_seen: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

class SwitchListResponse(BaseModel):
    data: list[SwitchRead]
    total: int
    page: int
    page_size: int
    total_pages: int