# discovery-service/app/middleware/logging_middleware.py
import logging
import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.middleware.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log chaque requête HTTP :
    - Méthode, path, status code, durée
    - Request ID pour tracer les requêtes
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Générer un ID unique pour tracer la requête
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Log de la requête entrante
        logger.info(
            "[HTTP] → %s %s (id=%s, client=%s)",
            request.method,
            request.url.path,
            request_id,
            request.client.host if request.client else "unknown",
            extra={
                "action": "http_request",
                "method": request.method,
                "path": request.url.path,
                "request_id": request_id,
            },
        )

        # Traiter la requête
        try:
            response = await call_next(request)
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "[HTTP] ✗ %s %s → ERROR after %dms: %s (id=%s)",
                request.method,
                request.url.path,
                elapsed_ms,
                e,
                request_id,
                extra={
                    "action": "http_error",
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": elapsed_ms,
                    "request_id": request_id,
                },
            )
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Log de la réponse
        log_fn = logger.info if response.status_code < 400 else logger.warning
        if response.status_code >= 500:
            log_fn = logger.error

        log_fn(
            "[HTTP] ← %s %s → %d (%dms) (id=%s)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
            extra={
                "action": "http_response",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
                "request_id": request_id,
            },
        )

        # Ajouter le request_id dans les headers de réponse
        response.headers["X-Request-ID"] = request_id
        return response