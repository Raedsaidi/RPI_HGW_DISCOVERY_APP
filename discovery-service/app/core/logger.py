# discovery-service/app/core/logger.py
"""
Helpers pour créer des loggers avec contexte enrichi.
Usage:
    from app.core.logger import get_logger, log_command, log_ssh, log_sync
    logger = get_logger(__name__)
"""
import logging
import time
from contextlib import contextmanager
from typing import Optional


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger standard pour le module."""
    return logging.getLogger(name)


# ─── Log SSH ────────────────────────────────────────────────
def log_ssh_connect(
    logger: logging.Logger,
    host: str,
    user: str,
    success: bool,
    elapsed_s: float,
    error: Optional[str] = None,
    via: Optional[str] = None,
):
    extra = {
        "device_ip": host,
        "action": "ssh_connect",
        "elapsed_s": round(elapsed_s, 3),
        "protocol": "ssh",
    }
    if via:
        extra["via"] = via

    if success:
        logger.info(
            "[SSH] ✓ Connected to %s (user=%s, elapsed=%.2fs)",
            host, user, elapsed_s,
            extra=extra,
        )
    else:
        extra["error"] = error or "unknown"
        logger.error(
            "[SSH] ✗ Failed to connect to %s (user=%s): %s",
            host, user, error,
            extra=extra,
        )


def log_ssh_command(
    logger: logging.Logger,
    host: str,
    command: str,
    output: str,
    elapsed_s: float,
    success: bool = True,
):
    preview = (output or "")[:200].replace("\n", "\\n")
    extra = {
        "device_ip": host,
        "action": "ssh_command",
        "command": command[:100],
        "output_preview": preview,
        "elapsed_s": round(elapsed_s, 3),
        "protocol": "ssh",
    }
    if success:
        logger.debug(
            "[SSH] CMD on %s: %r → %d chars (%.2fs)",
            host, command, len(output or ""), elapsed_s,
            extra=extra,
        )
    else:
        logger.warning(
            "[SSH] CMD FAILED on %s: %r",
            host, command,
            extra=extra,
        )


# ─── Log Telnet ─────────────────────────────────────────────
def log_telnet_connect(
    logger: logging.Logger,
    host: str,
    port: int,
    success: bool,
    elapsed_s: float,
    error: Optional[str] = None,
):
    extra = {
        "device_ip": host,
        "action": "telnet_connect",
        "elapsed_s": round(elapsed_s, 3),
        "protocol": "telnet",
    }
    if success:
        logger.info(
            "[TELNET] ✓ Connected to %s:%s (elapsed=%.2fs)",
            host, port, elapsed_s,
            extra=extra,
        )
    else:
        extra["error"] = error or "unknown"
        logger.error(
            "[TELNET] ✗ Failed to connect to %s:%s : %s",
            host, port, error,
            extra=extra,
        )


def log_telnet_command(
    logger: logging.Logger,
    host: str,
    command: str,
    output: str,
    elapsed_s: float,
    success: bool = True,
):
    preview = (output or "")[:200].replace("\n", "\\n")
    extra = {
        "device_ip": host,
        "action": "telnet_command",
        "command": command[:100],
        "output_preview": preview,
        "elapsed_s": round(elapsed_s, 3),
        "protocol": "telnet",
    }
    if success:
        logger.debug(
            "[TELNET] CMD on %s: %r → %d chars (%.2fs)",
            host, command, len(output or ""), elapsed_s,
            extra=extra,
        )
    else:
        logger.warning(
            "[TELNET] CMD FAILED on %s: %r",
            host, command,
            extra=extra,
        )


# ─── Log Sync/Discovery ──────────────────────────────────────
def log_sync_start(logger: logging.Logger, run_id: int, triggered_by: str):
    logger.info(
        "[SYNC] ═══ Discovery Run #%d STARTED (triggered_by=%s) ═══",
        run_id, triggered_by,
        extra={"run_id": run_id, "action": "sync_start"},
    )


def log_sync_end(
    logger: logging.Logger,
    run_id: int,
    status: str,
    elapsed_s: float,
    counters: dict,
):
    logger.info(
        "[SYNC] ═══ Discovery Run #%d FINISHED: status=%s, elapsed=%.1fs, "
        "sw_ok=%d sw_err=%d rpi_ok=%d rpi_err=%d hgw_ok=%d hgw_err=%d ═══",
        run_id, status, elapsed_s,
        counters.get("switches_ok", 0), counters.get("switches_err", 0),
        counters.get("rpis_ok", 0), counters.get("rpis_err", 0),
        counters.get("hgws_ok", 0), counters.get("hgws_err", 0),
        extra={"run_id": run_id, "action": "sync_end", "elapsed_s": elapsed_s, **counters},
    )


def log_switch_collect(
    logger: logging.Logger,
    switch_ip: str,
    run_id: int,
    mac_count: int,
    rpi_count: int,
    elapsed_s: float,
    success: bool,
    error: Optional[str] = None,
):
    extra = {
        "switch_ip": switch_ip,
        "run_id": run_id,
        "action": "switch_collect",
        "elapsed_s": round(elapsed_s, 3),
    }
    if success:
        logger.info(
            "[SWITCH] ✓ %s → %d MACs, %d RPis (%.2fs)",
            switch_ip, mac_count, rpi_count, elapsed_s,
            extra=extra,
        )
    else:
        extra["error"] = error or "unknown"
        logger.error(
            "[SWITCH] ✗ %s → FAILED: %s",
            switch_ip, error,
            extra=extra,
        )


def log_rpi_collect(
    logger: logging.Logger,
    rpi_ip: str,
    run_id: int,
    hostname: str,
    hgw_ip: Optional[str],
    elapsed_s: float,
    success: bool,
    error: Optional[str] = None,
):
    extra = {
        "rpi_ip": rpi_ip,
        "run_id": run_id,
        "action": "rpi_collect",
        "elapsed_s": round(elapsed_s, 3),
    }
    if hgw_ip:
        extra["hgw_ip"] = hgw_ip

    if success:
        logger.info(
            "[RPI] ✓ %s → hostname=%s, hgw=%s (%.2fs)",
            rpi_ip, hostname, hgw_ip, elapsed_s,
            extra=extra,
        )
    else:
        extra["error"] = error or "unknown"
        logger.error(
            "[RPI] ✗ %s → FAILED: %s",
            rpi_ip, error,
            extra=extra,
        )


def log_hgw_collect(
    logger: logging.Logger,
    hgw_ip: str,
    via_rpi: str,
    run_id: int,
    model: Optional[str],
    elapsed_s: float,
    success: bool,
    error: Optional[str] = None,
):
    extra = {
        "hgw_ip": hgw_ip,
        "rpi_ip": via_rpi,
        "run_id": run_id,
        "action": "hgw_collect",
        "elapsed_s": round(elapsed_s, 3),
    }
    if success:
        logger.info(
            "[HGW] ✓ %s (via %s) → model=%s (%.2fs)",
            hgw_ip, via_rpi, model, elapsed_s,
            extra=extra,
        )
    else:
        extra["error"] = error or "unknown"
        logger.error(
            "[HGW] ✗ %s (via %s) → FAILED: %s",
            hgw_ip, via_rpi, error,
            extra=extra,
        )


# ─── Context Manager pour mesurer le temps ──────────────────
@contextmanager
def timed(logger: logging.Logger, label: str, **extra_fields):
    """
    Usage:
        with timed(logger, "SSH connect", host="192.168.1.1") as t:
            # do stuff
        # logs automatiquement le temps
    """
    start = time.perf_counter()
    try:
        yield
        elapsed = time.perf_counter() - start
        logger.debug(
            "[TIMER] %s completed in %.3fs",
            label, elapsed,
            extra={"action": label, "elapsed_s": round(elapsed, 3), **extra_fields},
        )
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(
            "[TIMER] %s FAILED after %.3fs: %s",
            label, elapsed, e,
            extra={"action": label, "elapsed_s": round(elapsed, 3),
                   "error": str(e), **extra_fields},
        )
        raise