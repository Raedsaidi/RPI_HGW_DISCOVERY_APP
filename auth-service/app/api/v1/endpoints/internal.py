"""
Endpoint interne uniquement — appelé par discovery-service.
Protégé par INTERNAL_API_KEY (partagée via docker-compose env).
Jamais exposé publiquement.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.user import User, UserRole

router = APIRouter(tags=["internal"])


def _verify_internal_key(x_internal_key: str = Header(...)) -> None:
    """Vérifie la clé secrète partagée entre services."""
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )


@router.get(
    "/admins/emails",
    summary="[INTERNAL] Get active ADMIN emails for discovery alerts",
    dependencies=[Depends(_verify_internal_key)],
)
def get_admin_emails(db: Session = Depends(get_db)) -> dict:
    """
    Retourne les emails des users actifs avec role=ADMIN uniquement.
    SUPER_ADMIN est exclu (il gère le système, pas les alertes opérationnelles).
    """
    admins = (
        db.query(User)
        .filter(
            User.role == UserRole.ADMIN.value,
            User.is_active == True,
        )
        .all()
    )

    return {
        "emails": [u.email for u in admins],
        "count": len(admins),
    }