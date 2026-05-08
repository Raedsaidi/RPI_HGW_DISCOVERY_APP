from datetime import timedelta, datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from app.models.user import User, UserRole, UserProject
from app.models.refresh_token import RefreshToken

router = APIRouter(prefix="/auth", tags=["Auth"])

# =========================================================
# Reserved identifier for full-access assignment
# =========================================================
ALL_HGW_IDENTIFIER = "ALL"


# =========================================================
# Microservices helper: validate HGW exists via discovery-service
# =========================================================
def ensure_hgw_exists(identifier: str, request: Request) -> None:
    # ✅ Allow the reserved identifier "ALL" (no discovery validation)
    if (identifier or "").strip().upper() == ALL_HGW_IDENTIFIER:
        return

    base = getattr(settings, "DISCOVERY_SERVICE_URL", None) or "http://discovery_service:8001"
    base = base.rstrip("/")
    url = f"{base}/api/v1/hgws/{identifier}"

    auth_header = request.headers.get("authorization")
    headers = {"Authorization": auth_header} if auth_header else {}

    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(url, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"HGW validation failed (discovery service unreachable): {e}",
        )

    if r.status_code == 404:
        raise HTTPException(status_code=400, detail=f"Invalid HGW identifier '{identifier}' (not found).")

    if r.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="HGW validation failed (discovery rejected JWT). Ensure JWT_SECRET_KEY is the same in both services.",
        )

    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"HGW validation failed (discovery error {r.status_code}): {r.text}",
        )


def _normalize_identifiers(ids: list[str]) -> list[str]:
    """
    strip + remove empties + dedupe while keeping order
    + normalize ALL

    IMPORTANT:
    - "ALL" can coexist with other identifiers.
      Example: ["ALL", "serial1", "serial2"] is valid.
    """
    out: list[str] = []
    seen: set[str] = set()

    for x in ids:
        v = (x or "").strip()
        if not v:
            continue

        if v.upper() == ALL_HGW_IDENTIFIER:
            v = ALL_HGW_IDENTIFIER

        if v in seen:
            continue
        seen.add(v)
        out.append(v)

    return out


def _legacy_project_hgw_ip(ids: list[str]) -> str | None:
    """
    project_hgw_ip is legacy (1 value).
    - Do not store ALL there.
    - Pick the first identifier != ALL, else None.
    """
    for v in ids:
        if v != ALL_HGW_IDENTIFIER:
            return v
    return None


# =========================================================
# Login / refresh / logout
# =========================================================

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form_data.username.strip()
    password = form_data.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    if not (3 <= len(username) <= 32):
        raise HTTPException(status_code=400, detail="Username must be between 3 and 32 characters.")
    if not (8 <= len(password) <= 72):
        raise HTTPException(status_code=400, detail="Password must be between 8 and 72 characters.")

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User account is disabled.")

    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )

    refresh_token = create_refresh_token_for_user(db, user)

    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
def refresh_access_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    raw_refresh_token = body.refresh_token
    if not raw_refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token missing.")

    stored: RefreshToken | None = get_stored_refresh_token(db, raw_refresh_token)
    if stored is None or stored.revoked:
        raise HTTPException(status_code=401, detail="Refresh token invalid.")

    expires_at = stored.expires_at
    now_utc = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now_utc:
        revoke_refresh_token(db, stored)
        raise HTTPException(status_code=401, detail="Refresh token expired.")

    user = stored.user
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or disabled user.")

    revoke_refresh_token(db, stored)

    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires,
    )
    new_refresh_token = create_refresh_token_for_user(db, user)

    return Token(access_token=access_token, refresh_token=new_refresh_token)


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


# =========================================================
# /me
# =========================================================

@router.get("/me", response_model=UserRead)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .options(selectinload(User.user_projects))
        .filter(User.id == current_user.id)
        .first()
    )
    return user


# =========================================================
# Users management (ADMIN/SUPER_ADMIN)
# =========================================================

@router.post("/users", response_model=UserRead, status_code=201)
def create_user_admin(
    user_in: AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # ADMIN cannot create SUPER_ADMIN
    if current_user.role == UserRole.ADMIN.value and user_in.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="An ADMIN cannot create SUPER_ADMIN accounts.")

    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")

    existing_email = db.query(User).filter(User.email == user_in.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already in use.")

    # --- project identifiers (0..n) ---
    ids = list(user_in.project_hgws or [])
    # legacy fallback
    if not ids and user_in.project_hgw_ip:
        ids = [user_in.project_hgw_ip]
    ids = _normalize_identifiers(ids)

    for identifier in ids:
        ensure_hgw_exists(identifier, request)

    user = User(
        username=user_in.username,
        email=str(user_in.email),
        full_name=user_in.full_name,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role.value,
        is_active=True,
        # legacy column: do NOT store "ALL" there
        project_hgw_ip=_legacy_project_hgw_ip(ids),
    )

    db.add(user)
    db.flush()  # get user.id without committing yet

    for identifier in ids:
        db.add(UserProject(user_id=user.id, hgw_identifier=identifier))

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
    q = db.query(User).options(
        selectinload(User.refresh_tokens),
        selectinload(User.user_projects),
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
                project_hgws=u.project_hgws,
                project_hgw_ip=getattr(u, "project_hgw_ip", None),  # legacy
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = (
        db.query(User)
        .options(selectinload(User.user_projects))
        .filter(User.id == user_id)
        .first()
    )
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

    # Interdire de changer le rôle d'un SUPER_ADMIN
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
            raise HTTPException(status_code=400, detail="This email is already in use.")
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

    # =========================================================
    # Projects (0..n) — IMPORTANT: flush after clear()
    # =========================================================

    # Si project_hgws est fourni => remplace toute la liste (même [] => clear)
    if "project_hgws" in user_in.model_fields_set:
        ids = _normalize_identifiers(list(user_in.project_hgws or []))

        # validate all identifiers (ALL is allowed)
        for identifier in ids:
            ensure_hgw_exists(identifier, request)

        # delete old rows first
        user.user_projects.clear()
        db.flush()

        # insert new rows
        for identifier in ids:
            user.user_projects.append(UserProject(hgw_identifier=identifier))

        # legacy column (do NOT store ALL there)
        user.project_hgw_ip = _legacy_project_hgw_ip(ids)

    # Support legacy (si quelqu’un envoie encore project_hgw_ip)
    elif "project_hgw_ip" in user_in.model_fields_set:
        if user_in.project_hgw_ip is None or user_in.project_hgw_ip.strip() == "":
            user.user_projects.clear()
            db.flush()
            user.project_hgw_ip = None
        else:
            identifier = user_in.project_hgw_ip.strip()

            # legacy can't express a list: treat "ALL" as "ALL only"
            if identifier.upper() == ALL_HGW_IDENTIFIER:
                user.user_projects.clear()
                db.flush()
                user.user_projects.append(UserProject(hgw_identifier=ALL_HGW_IDENTIFIER))
                user.project_hgw_ip = None
            else:
                ensure_hgw_exists(identifier, request)

                user.user_projects.clear()
                db.flush()

                user.user_projects.append(UserProject(hgw_identifier=identifier))
                user.project_hgw_ip = identifier

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    if user.role == UserRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="An account with SUPER_ADMIN role cannot be deleted.")

    if current_user.role == UserRole.ADMIN.value and user.role != UserRole.USER.value:
        raise HTTPException(status_code=403, detail="An ADMIN can only delete USER accounts.")

    db.delete(user)
    db.commit()
    return


@router.get("/internal/users/{username}/hgws")
def get_user_hgws_internal(
    username: str,
    db: Session = Depends(get_db),
):
    """
    Endpoint INTERNE appelé par le discovery-service (topology_service)
    pour récupérer les HGW identifiers d'un utilisateur.

    Retourne : ["ALL", "serial123", ...] ou ["serial123", ...] etc.
    """
    user = (
        db.query(User)
        .options(selectinload(User.user_projects))
        .filter(User.username == username)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return user.project_hgws