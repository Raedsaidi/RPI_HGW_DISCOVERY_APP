# auth-service/app/core/config.py
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    APP_NAME: str = Field(default="auth-service")
    ENVIRONMENT: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")

    # MySQL
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=3306)
    DB_NAME: str = Field(default="auth_service")
    DB_USER: str = Field(default="root")
    DB_PASSWORD: str = Field(default="root")

    JWT_SECRET_KEY: str = Field(
        default="7f8d2a1e4b9c6d0f3a8e5b2c1d4f9a0e7c6b3f1a2d9e5c4b8a1f0d7e2c3b4a6"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    INITIAL_SUPERADMIN_USERNAME: str = Field(default="superadmin")
    INITIAL_SUPERADMIN_PASSWORD: str = Field(default="SuperAdmin123!")
    INITIAL_SUPERADMIN_EMAIL: str = Field(default="superadmin@example.com")
    INITIAL_SUPERADMIN_FULL_NAME: str = Field(default="Super Admin")
    DISCOVERY_SERVICE_URL: str = Field(default="http://discovery_service:8001")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


def get_settings() -> Settings:
    return Settings(
        APP_NAME=os.getenv("APP_NAME", "auth-service"),
        ENVIRONMENT=os.getenv("ENVIRONMENT", "dev"),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        DB_HOST=os.getenv("DB_HOST", "localhost"),
        DB_PORT=int(os.getenv("DB_PORT", "3306")),
        DB_NAME=os.getenv("DB_NAME", "auth_service"),
        DB_USER=os.getenv("DB_USER", "root"),
        DB_PASSWORD=os.getenv("DB_PASSWORD", "root"),
        JWT_SECRET_KEY=os.getenv(
            "JWT_SECRET_KEY",
            "7f8d2a1e4b9c6d0f3a8e5b2c1d4f9a0e7c6b3f1a2d9e5c4b8a1f0d7e2c3b4a6",
        ),
        JWT_ALGORITHM=os.getenv("JWT_ALGORITHM", "HS256"),
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES=int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        ),
        JWT_REFRESH_TOKEN_EXPIRE_DAYS=int(
            os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
        ),
        INITIAL_SUPERADMIN_USERNAME=os.getenv(
            "INITIAL_SUPERADMIN_USERNAME", "superadmin"
        ),
        INITIAL_SUPERADMIN_PASSWORD=os.getenv(
            "INITIAL_SUPERADMIN_PASSWORD", "SuperAdmin123!"
        ),
        INITIAL_SUPERADMIN_EMAIL=os.getenv(
            "INITIAL_SUPERADMIN_EMAIL", "superadmin@example.com"
        ),
        INITIAL_SUPERADMIN_FULL_NAME=os.getenv(
            "INITIAL_SUPERADMIN_FULL_NAME", "Super Admin"
        ),
        DISCOVERY_SERVICE_URL=os.getenv(
            "DISCOVERY_SERVICE_URL", "http://discovery_service:8001"
        ),
    )


settings = get_settings()