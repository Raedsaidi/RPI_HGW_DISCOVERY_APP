# app/schemas/user_schema.py
from enum import Enum as PyEnum


class UserRole(str, PyEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    USER = "USER"