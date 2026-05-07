from datetime import datetime
from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.models.user import UserRole


# =========================================================
# Types réutilisables
# =========================================================

UsernameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=32),
]

FullNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

PasswordStr = Annotated[
    str,
    StringConstraints(min_length=8, max_length=72),
]

RefreshTokenStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
]

HgwIdentifierStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


# =========================================================
# Helpers
# =========================================================

def contains_letter(value: str) -> bool:
    return any(ch.isalpha() for ch in value)


def is_only_digits_ignoring_spaces(value: str) -> bool:
    compact = value.replace(" ", "")
    return bool(compact) and compact.isdigit()


def is_valid_full_name(value: str) -> bool:
    return all(ch.isalpha() or ch == " " for ch in value)


def validate_password_rules(v: str) -> str:
    if any(ch.isspace() for ch in v):
        raise ValueError("Password cannot contain spaces.")
    if not any(ch.islower() for ch in v):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not any(ch.isupper() for ch in v):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(ch.isdigit() for ch in v):
        raise ValueError("Password must contain at least one digit.")
    if not any(not ch.isalnum() for ch in v):
        raise ValueError("Password must contain at least one special character.")
    return v


# =========================================================
# Bases communes
# =========================================================

class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ORMReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# =========================================================
# Tokens
# =========================================================

class Token(BaseModel):
    access_token: str
    refresh_token: str


class RefreshTokenRequest(StrictInputModel):
    refresh_token: RefreshTokenStr

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, v: str) -> str:
        if any(ch.isspace() for ch in v):
            raise ValueError("The refresh token cannot contain spaces.")
        return v


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None


# =========================================================
# Base commune pour création user (admin uniquement)
# =========================================================

class UserInputBase(StrictInputModel):
    username: UsernameStr
    email: EmailStr
    full_name: FullNameStr
    password: PasswordStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if is_only_digits_ignoring_spaces(v):
            raise ValueError("The username cannot be composed only of digits.")
        if any(ch in v for ch in ("\n", "\r", "\t")):
            raise ValueError("The username cannot contain newline or tab characters.")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: EmailStr) -> EmailStr:
        if len(str(v)) > 254:
            raise ValueError("The email address is too long.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        if not contains_letter(v):
            raise ValueError("The full name must contain at least one letter and cannot be numeric.")
        if not is_valid_full_name(v):
            raise ValueError("The full name can only contain letters and spaces.")
        if "  " in v:
            raise ValueError("The full name cannot contain double spaces.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_rules(v)


# =========================================================
# Création user via ADMIN / SUPER_ADMIN
# =========================================================

class AdminUserCreate(UserInputBase):
    role: UserRole

    # ✅ NEW: 0..n HGWs
    project_hgws: list[HgwIdentifierStr] = Field(default_factory=list)

    # legacy (optional) : ancien champ 1 seule valeur
    project_hgw_ip: Optional[HgwIdentifierStr] = None


# =========================================================
# UPDATE user via ADMIN / SUPER_ADMIN (sans username)
# =========================================================

class AdminUserUpdate(StrictInputModel):
    email: Optional[EmailStr] = None
    full_name: Optional[FullNameStr] = None
    password: Optional[PasswordStr] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None

    # ✅ NEW: si fourni => remplace la liste complète, [] => clear
    project_hgws: Optional[list[HgwIdentifierStr]] = None

    # legacy
    project_hgw_ip: Optional[HgwIdentifierStr] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[EmailStr]) -> Optional[EmailStr]:
        if v is None:
            return None
        if len(str(v)) > 254:
            raise ValueError("The email address is too long.")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not contains_letter(v):
            raise ValueError("The full name must contain at least one letter and cannot be numeric.")
        if not is_valid_full_name(v):
            raise ValueError("The full name can only contain letters and spaces.")
        if "  " in v:
            raise ValueError("The full name cannot contain double spaces.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_password_rules(v)


# =========================================================
# Lecture user standard
# =========================================================

class UserRead(ORMReadModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool

    # ✅ NEW
    project_hgws: list[str] = Field(default_factory=list)

    # legacy (optional read)
    project_hgw_ip: Optional[str] = None

    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


# =========================================================
# Lecture user côté admin
# =========================================================

class UserAdminRead(ORMReadModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    password_hash: str

    # ✅ NEW
    project_hgws: list[str] = Field(default_factory=list)

    # legacy (optional read)
    project_hgw_ip: Optional[str] = None

    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UserList(BaseModel):
    users: list[UserAdminRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChangeRoleRequest(StrictInputModel):
    role: UserRole