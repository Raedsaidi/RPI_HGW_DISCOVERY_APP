import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Roles autorisés à modifier
WRITE_ROLES = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER"}
READ_ROLES = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "USER"}


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning("[SECURITY] JWT decode failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    payload = _decode_token(token)
    username = payload.get("sub")
    role = payload.get("role")

    if not username or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    return {"username": username, "role": role}


async def require_read_access(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] not in READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read access required.",
        )
    return current_user


async def require_write_access(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required (ADMIN, PROJECT_MANAGER or SUPER_ADMIN).",
        )
    return current_user


async def require_super_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SUPER_ADMIN privileges required.",
        )
    return current_user