# discovery-service/app/core/logging_config.py
import logging
import logging.handlers
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


# ─── Dossier logs ───────────────────────────────────────────
LOGS_DIR = Path("/app/logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Formatter JSON structuré ───────────────────────────────
class JSONFormatter(logging.Formatter):
    """
    Format chaque log en JSON sur une ligne.
    Compatible avec Dozzle, Loki, ELK, etc.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Ajouter les champs extra si présents
        extra_fields = [
            "device_type", "device_ip", "stage",
            "run_id", "switch_ip", "rpi_ip", "hgw_ip",
            "command", "output_preview", "elapsed_s",
            "protocol", "action", "user", "status_code",
            "method", "path", "duration_ms",
        ]
        for field in extra_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        # Ajouter les exceptions
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.exc_text:
            log_entry["exception_text"] = record.exc_text

        return json.dumps(log_entry, ensure_ascii=False)


# ─── Formatter lisible pour console ─────────────────────────
class ColorFormatter(logging.Formatter):
    """Format coloré pour la console Docker/terminal."""

    COLORS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET

        # Format de base
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        base = f"{color}[{record.levelname}]{reset} {ts} {record.name}: {record.getMessage()}"

        # Champs extra importants
        extras = []
        for field in ["device_ip", "run_id", "switch_ip", "rpi_ip", "hgw_ip",
                      "command", "elapsed_s", "action"]:
            if hasattr(record, field):
                extras.append(f"{field}={getattr(record, field)}")

        if extras:
            base += f" | {' '.join(extras)}"

        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"

        return base


def setup_logging(
    app_name: str = "discovery-service",
    log_level: str = "INFO",
    enable_json: bool = True,
) -> None:
    """
    Configure le système de logs global.
    - Console  : format coloré lisible (visible dans Dozzle)
    - Fichier  : format JSON structuré (rotatif, 10MB x 5 fichiers)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Supprimer les handlers existants
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # ── Handler Console (stdout → Dozzle le lit) ──────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    if enable_json:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ColorFormatter())
    root.addHandler(console_handler)

    # ── Handler Fichier JSON (rotatif) ────────────────────────
    log_file = LOGS_DIR / f"{app_name}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    # ── Fichier séparé pour les erreurs ──────────────────────
    error_file = LOGS_DIR / f"{app_name}.errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        filename=str(error_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root.addHandler(error_handler)

    # ── Fichier séparé pour la synchronisation ────────────────
    sync_file = LOGS_DIR / f"{app_name}.sync.log"
    sync_handler = logging.handlers.RotatingFileHandler(
        filename=str(sync_file),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    sync_handler.setLevel(level)
    sync_handler.setFormatter(JSONFormatter())

    # Ajouter uniquement aux loggers de sync/discovery
    for logger_name in ["app.services.discovery_service",
                        "app.services.sync_service",
                        "app.infrastructure.ssh_manager",
                        "app.infrastructure.telnet_manager",
                        "app.infrastructure.netgear_client",
                        "app.infrastructure.rpi_client",
                        "app.infrastructure.hgw_client"]:
        lg = logging.getLogger(logger_name)
        lg.addHandler(sync_handler)

    # ── Réduire le bruit des libs externes ───────────────────
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        "[LOGGING] Configured: level=%s, dir=%s, json=%s",
        log_level, LOGS_DIR, enable_json,
    )