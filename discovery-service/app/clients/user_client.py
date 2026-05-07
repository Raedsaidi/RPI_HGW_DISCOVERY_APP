# app/clients/user_client.py

import logging
from typing import Optional
from functools import lru_cache

import httpx
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


class UserServiceClient:
    """
    Client HTTP vers le User Service.
    Remplace tous les db.query(User) du topology_service.
    """

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_user_hgw_identifiers(self, username: str) -> list[str]:
        """
        Appelle GET /internal/users/{username}/hgws sur le User Service.
        Retourne la liste des hgw_identifiers assignés à l'utilisateur.
        Retourne [] si l'utilisateur n'existe pas.

        Remplace ce code qui ne fonctionne plus :
            user = db.query(User).filter(User.username == username).first()
            return user.project_hgws
        """

        url = f"{self.base_url}/api/v1/auth/internal/users/{username}/hgws"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    headers={"X-Service-Name": "discovery-service"},
                )

            # user non trouvé → liste vide
            if response.status_code == 404:
                logger.warning(
                    "[UserClient] User '%s' not found in user-service.", username
                )
                return []

            if response.status_code != 200:
                logger.error(
                    "[UserClient] Unexpected status %s for user '%s': %s",
                    response.status_code,
                    username,
                    response.text,
                )
                raise HTTPException(
                    status_code=502,
                    detail="User service returned an unexpected error.",
                )

            data = response.json()

            # Le user-service retourne soit une liste directement
            # soit un objet {"hgws": [...]}
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("hgws", data.get("project_hgws", []))

            return []

        except httpx.TimeoutException:
            logger.error(
                "[UserClient] Timeout calling user-service for username='%s'", username
            )
            raise HTTPException(
                status_code=504,
                detail="User service timeout. Please try again.",
            )

        except httpx.RequestError as exc:
            logger.error("[UserClient] Cannot reach user-service: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Cannot reach user service.",
            )


@lru_cache(maxsize=1)
def get_user_client() -> UserServiceClient:
    """
    Singleton injecté par FastAPI via Depends().
    Créé une seule fois au démarrage.
    """
    return UserServiceClient(
        base_url=settings.AUTH_SERVICE_URL,
        timeout=settings.AUTH_SERVICE_TIMEOUT,
    )