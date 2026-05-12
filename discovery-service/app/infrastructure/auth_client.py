"""
Client HTTP interne vers auth-service.
Récupère les emails des ADMINs actifs pour les alertes discovery.
"""
import httpx
from typing import Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class AuthClient:
    """
    Appelle auth-service via HTTP interne (docker network).
    Timeout court : on ne bloque pas la discovery pour un email.
    """

    def __init__(self):
        self.base_url = settings.AUTH_SERVICE_URL.rstrip("/")
        self.internal_key = settings.INTERNAL_API_KEY
        self.timeout = 10  # secondes

    def get_admin_emails(self) -> list[str]:
        """
        Retourne la liste des emails ADMIN actifs.
        Retourne [] en cas d'erreur (jamais bloquant).
        """
        url = f"{self.base_url}/internal/admins/emails"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    headers={"x-internal-key": self.internal_key},
                )

            if response.status_code == 200:
                data = response.json()
                emails = data.get("emails", [])
                logger.info(
                    "[AUTH_CLIENT] ✓ Fetched %d admin email(s) from auth-service",
                    len(emails),
                    extra={"action": "auth_client_emails_ok", "count": len(emails)},
                )
                return emails

            logger.warning(
                "[AUTH_CLIENT] ✗ auth-service returned %d: %s",
                response.status_code,
                response.text[:200],
                extra={
                    "action": "auth_client_emails_error",
                    "status_code": response.status_code,
                },
            )
            return []

        except httpx.TimeoutException:
            logger.error(
                "[AUTH_CLIENT] ✗ Timeout fetching admin emails from auth-service",
                extra={"action": "auth_client_timeout"},
            )
            return []

        except Exception as e:
            logger.error(
                "[AUTH_CLIENT] ✗ Failed to fetch admin emails: %s",
                e,
                exc_info=True,
                extra={"action": "auth_client_error"},
            )
            return []