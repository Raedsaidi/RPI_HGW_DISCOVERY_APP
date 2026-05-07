from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import List

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UserRole(str, PyEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    USER = "USER"


class UserProject(Base):
    """
    Link table: a user can have 0..n HGW identifiers.
    hgw_identifier should be a UNIQUE identifier (serial_number preferred).
    """
    __tablename__ = "user_projects"
    __table_args__ = (
        UniqueConstraint("user_id", "hgw_identifier", name="uq_user_hgw"),
        Index("ix_user_projects_user_id", "user_id"),
        Index("ix_user_projects_hgw_identifier", "hgw_identifier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hgw_identifier: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="user_projects")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # --- NEW: many projects ---
    user_projects: Mapped[List["UserProject"]] = relationship(
        "UserProject",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    project_hgw_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    @property
    def project_hgws(self) -> list[str]:
        """
        Convenience property for Pydantic responses (0..n).
        """
        return [p.hgw_identifier for p in (self.user_projects or [])]