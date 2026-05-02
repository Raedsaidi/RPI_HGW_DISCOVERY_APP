from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "discovery-service"
    ENVIRONMENT: str = "dev"
    LOG_LEVEL: str = "INFO"

    # MySQL
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str = "discovery_service"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    # Bastion / Piserver
    PISERVER_HOST: str = "10.255.25.15"
    PISERVER_USER: str = "root"
    PISERVER_PASS: str = "sah"
    PISERVER_FILE: str = "/etc/dnsmasq.d/piserver"

    # Switch defaults
    SWITCH_TELNET_PORT: int = 60000
    SWITCH_TELNET_USER: str = "admin"
    SWITCH_TELNET_PASS: str = "password"

    # RPi defaults — credential primaire
    RPI_SSH_USER: str = "pi"
    RPI_SSH_PASS: str = "raspberry"

    # ── NOUVEAU : RPi fallback credentials ───────────────────
    RPI_SSH_FALLBACK_USER: str = "root"
    RPI_SSH_FALLBACK_PASS: str = "sah"
    # ─────────────────────────────────────────────────────────

    # HGW defaults
    HGW_SSH_USER: str = "root"
    HGW_SSH_PASS: str = "sah"

    # Scheduler
    SYNC_HOUR: int = 4
    SYNC_MINUTE: int = 0
    SYNC_ENABLED: bool = True
    SYNC_TIMEZONE: str = "UTC"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()