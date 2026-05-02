import re
from datetime import timedelta, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_

from app.core.config import settings
from app.core.db import get_db
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_user,
    require_admin,
    create_refresh_token_for_user,
    get_stored_refresh_token,
    revoke_refresh_token,
)
from app.models.auth import (
    Token,
    AdminUserCreate,
    AdminUserUpdate,
    UserRead,
    UserAdminRead,
    UserList,
    RefreshTokenRequest,
)
from app.models.user import User, UserRole
from app.models.refresh_token import RefreshToken

router = APIRouter(prefix="/auth", tags=["Auth"])


# ----- Login / refresh / logout -----

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form_data.username.strip()
    password = form_data.password

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required.",
        )

    if not (3 <= len(username) <= 32):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be between 3 and 32 characters.",
        )
    if not (8 <= len(password) <= 72):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be between 8 and 72 characters.",
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is disabled.",
        )

    access_token_expires = timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )

    refresh_token = create_refresh_token_for_user(db, user)

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
def refresh_access_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    raw_refresh_token = body.refresh_token
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token missing.",
        )

    stored: RefreshToken | None = get_stored_refresh_token(db, raw_refresh_token)
    if stored is None or stored.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalid.",
        )

    expires_at = stored.expires_at 
    now_utc = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now_utc:
        revoke_refresh_token(db, stored)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired.",
        )

    user = stored.user
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled user.",
        )

    revoke_refresh_token(db, stored)

    access_token_expires = timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )

    new_refresh_token = create_refresh_token_for_user(db, user)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", status_code=204)
def logout(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    raw_refresh_token = body.refresh_token
    if not raw_refresh_token:
        return

    stored: RefreshToken | None = get_stored_refresh_token(db, raw_refresh_token)
    if stored is None or stored.revoked:
        return

    revoke_refresh_token(db, stored)
    return


# ----- /me -----

@router.get("/me", response_model=UserRead)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    return user


# Dans create_user_admin — modifier les règles de création
@router.post("/users", response_model=UserRead, status_code=201)
def create_user_admin(
    user_in: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    - SUPER_ADMIN : peut créer tous les rôles
    - ADMIN       : peut créer ADMIN, PROJECT_MANAGER, USER
    - PROJECT_MANAGER : ne peut pas créer des comptes (pas accès à cet endpoint)
    """
    # ADMIN ne peut pas créer SUPER_ADMIN
    if (
        current_user.role == UserRole.ADMIN.value
        and user_in.role == UserRole.SUPER_ADMIN
    ):
        raise HTTPException(
            status_code=403,
            detail="An ADMIN cannot create SUPER_ADMIN accounts.",
        )

    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    existing_email = db.query(User).filter(User.email == user_in.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already in use.")

    user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=UserList)
def list_users(
    search: str | None = Query(None, min_length=1, max_length=200),
    role: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Liste paginée de tous les users (ADMIN et SUPER_ADMIN).
    Supports:
    - server-side search by username, email, full_name
    - optional role filtering
    - backend pagination
    """
    q = db.query(User).options(
        selectinload(User.refresh_tokens),
    )

    if role and role != "ALL":
        q = q.filter(User.role == role)

    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
        )

    total = q.count()
    total_pages = max((total + page_size - 1) // page_size, 1)

    offset = (page - 1) * page_size

    users = (
        q.order_by(User.id.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    admin_reads: list[UserAdminRead] = []
    for u in users:
        admin_reads.append(
            UserAdminRead(
                id=u.id,
                username=u.username,
                email=u.email,
                full_name=u.full_name,
                role=UserRole(u.role),
                is_active=u.is_active,
                password_hash=u.password_hash,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
        )

    return UserList(
        users=admin_reads,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user_admin(
    user_id: int,
    user_in: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # ADMIN ne peut modifier que des USER
    if current_user.role == UserRole.ADMIN.value and user.role != UserRole.USER.value:
        raise HTTPException(status_code=403, detail="An ADMIN can only modify USER accounts.")

    # Si on tente de modifier role => SUPER_ADMIN only
    if user_in.role is not None and current_user.role != UserRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Only a SUPER_ADMIN can change roles.")

    # Protéger SUPER_ADMIN contre modifications par non superadmin
    if user.role == UserRole.SUPER_ADMIN.value and current_user.role != UserRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Impossible to modify a SUPER_ADMIN.")

    # Interdire de changer ton propre rôle
    if user_in.role is not None and user.id == current_user.id and user_in.role.value != user.role:
        raise HTTPException(status_code=403, detail="You cannot modify your own role.")

    # Interdire de changer le rôle d'un SUPER_ADMIN (même par SUPER_ADMIN)
    if user_in.role is not None and user.role == UserRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Impossible to modify the role of a SUPER_ADMIN.")

    # --- role ---
    if user_in.role is not None:
        user.role = user_in.role.value

    # --- email ---
    if user_in.email is not None:
        existing_email = (
            db.query(User)
            .filter(User.email == user_in.email, User.id != user.id)
            .first()
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already in use.",
            )
        user.email = str(user_in.email)

    # --- full_name ---
    if user_in.full_name is not None:
        user.full_name = user_in.full_name

    # --- password ---
    if user_in.password is not None:
        user.password_hash = get_password_hash(user_in.password)

    # --- is_active ---
    if user_in.is_active is not None:
        user.is_active = user_in.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Suppression d'un user.
    - Nobody can delete a SUPER_ADMIN.
    - ADMIN : ne peut supprimer que des USER.
    - SUPER_ADMIN : peut supprimer ADMIN et USER, mais not other SUPER_ADMIN.
    - Nobody can delete themselves.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Cannot delete yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )

    # Nobody can delete a SUPER_ADMIN
    if user.role == UserRole.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=403,
            detail="Un account with SUPER_ADMIN role cannot be deleted.",
        )

    # ADMIN can only delete USER
    if current_user.role == UserRole.ADMIN.value:
        if user.role != UserRole.USER.value:
            raise HTTPException(
                status_code=403,
                detail="An ADMIN can only delete USER accounts.",
            )

    db.delete(user)
    db.commit()
    return