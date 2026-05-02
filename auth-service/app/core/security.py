from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.auth import TokenData
from app.models.user import User, UserRole
from app.models.refresh_token import RefreshToken

# On utilise pbkdf2_sha256 au lieu de bcrypt pour éviter la limite 72 bytes
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ── Role hierarchy ──────────────────────────────────────────
WRITE_ROLES = {
    UserRole.SUPER_ADMIN.value,
    UserRole.ADMIN.value,
    UserRole.PROJECT_MANAGER.value,
}
READ_ROLES = {
    UserRole.SUPER_ADMIN.value,
    UserRole.ADMIN.value,
    UserRole.PROJECT_MANAGER.value,
    UserRole.USER.value,
}


# ── Password hashing (aucune limite de longueur) ────────────

def get_password_hash(password: str) -> str:
    """
    Hash du mot de passe avec pbkdf2_sha256.
    Compatible avec n'importe quelle longueur de mot de passe.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Vérifie qu'un mot de passe en clair correspond au hash stocké.
    """
    return pwd_context.verify(plain_password, password_hash)


# ── Access token (JWT) ──────────────────────────────────────

def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


# ── Refresh token helpers ────────────────────────────────────

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def get_refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token_for_user(db: Session, user: User) -> str:
    raw_token = generate_refresh_token()
    token_hash = get_refresh_token_hash(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    rt = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rt)
    db.commit()
    return raw_token


def get_stored_refresh_token(
    db: Session, raw_token: str
) -> Optional[RefreshToken]:
    token_hash = get_refresh_token_hash(raw_token)
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )


def revoke_refresh_token(db: Session, refresh_token: RefreshToken) -> None:
    refresh_token.revoked = True
    db.add(refresh_token)
    db.commit()


# ── Current user & roles ─────────────────────────────────────

async def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
        _ = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SUPER_ADMIN privileges required.",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """ADMIN or SUPER_ADMIN."""
    if current_user.role not in (
        UserRole.ADMIN.value,
        UserRole.SUPER_ADMIN.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN or SUPER_ADMIN privileges required.",
        )
    return current_user


async def require_write_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """SUPER_ADMIN, ADMIN, PROJECT_MANAGER."""
    if current_user.role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required (ADMIN, PROJECT_MANAGER or SUPER_ADMIN).",
        )
    return current_user


async def require_read_access(
    current_user: User = Depends(get_current_user),
) -> User:
    """All authenticated users."""
    if current_user.role not in READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read access required.",
        )
    return current_user