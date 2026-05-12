#!/usr/bin/env python3
"""
Script de test manuel pour le système d'email discovery.

Usage:
    # Depuis la racine du discovery-service
    python scripts/test_email_manual.py

    # Avec options
    python scripts/test_email_manual.py --step all
    python scripts/test_email_manual.py --step config
    python scripts/test_email_manual.py --step auth
    python scripts/test_email_manual.py --step email
    python scripts/test_email_manual.py --step full

Prérequis:
    - .env configuré (RESEND_API_KEY, INTERNAL_API_KEY, AUTH_SERVICE_URL, ...)
    - auth-service accessible (docker up ou local)
"""

import argparse
import sys
import os
import time

# ── Ajouter le répertoire racine au path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Couleurs terminal ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET} {msg}")
def err(msg: str)  -> None: print(f"  {RED}✗{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg: str) -> None: print(f"  {CYAN}→{RESET} {msg}")

def section(title: str) -> None:
    print(f"\n{BOLD}{BLUE}{'─' * 55}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 55}{RESET}")

def result(success: bool, label: str) -> None:
    if success:
        print(f"\n  {GREEN}{BOLD}[PASS]{RESET} {label}")
    else:
        print(f"\n  {RED}{BOLD}[FAIL]{RESET} {label}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Vérification configuration
# ══════════════════════════════════════════════════════════════════════════════

def test_config() -> bool:
    section("STEP 1 — Vérification de la configuration")

    try:
        from app.core.config import settings
        ok("Import settings OK")
    except Exception as e:
        err(f"Import settings FAILED: {e}")
        return False

    checks = {
        "RESEND_API_KEY":    (settings.RESEND_API_KEY,    lambda v: v.startswith("re_"), "doit commencer par 're_'"),
        "ALERT_EMAIL_FROM":  (settings.ALERT_EMAIL_FROM,  lambda v: "@" in v,            "doit contenir '@'"),
        "AUTH_SERVICE_URL":  (settings.AUTH_SERVICE_URL,  lambda v: v.startswith("http"),"doit commencer par 'http'"),
        "INTERNAL_API_KEY":  (settings.INTERNAL_API_KEY,  lambda v: len(v) >= 10,        "doit faire >= 10 caractères"),
        "JWT_SECRET_KEY":    (settings.JWT_SECRET_KEY,    lambda v: len(v) >= 10,        "doit faire >= 10 caractères"),
    }

    all_ok = True
    for name, (value, validator, hint) in checks.items():
        display = value[:6] + "..." if value and len(value) > 6 else (value or "")
        if not value:
            err(f"{name} = '{value}' → NON CONFIGURÉ")
            all_ok = False
        elif not validator(value):
            warn(f"{name} = '{display}' → {hint}")
            all_ok = False
        else:
            ok(f"{name} = '{display}...' → OK")

    # Infos non critiques
    print()
    info(f"APP_NAME        = {settings.APP_NAME}")
    info(f"ENVIRONMENT     = {settings.ENVIRONMENT}")
    info(f"AUTH_SERVICE_URL= {settings.AUTH_SERVICE_URL}")
    info(f"DATABASE_URL    = {settings.DATABASE_URL[:40]}...")

    result(all_ok, "Configuration")
    return all_ok


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Test AuthClient (récupération emails admins)
# ══════════════════════════════════════════════════════════════════════════════

def test_auth_client() -> tuple[bool, list[str]]:
    section("STEP 2 — Test AuthClient → auth-service")

    try:
        from app.infrastructure.auth_client import AuthClient
        ok("Import AuthClient OK")
    except Exception as e:
        err(f"Import AuthClient FAILED: {e}")
        return False, []

    from app.core.config import settings
    info(f"Appel vers : {settings.AUTH_SERVICE_URL}/internal/admins/emails")
    info(f"Timeout    : {settings.AUTH_SERVICE_TIMEOUT}s")
    info(f"Clé interne: {settings.INTERNAL_API_KEY[:6]}...")

    start = time.perf_counter()
    try:
        client = AuthClient()
        emails = client.get_admin_emails()
        elapsed = time.perf_counter() - start

        if emails:
            ok(f"Réponse reçue en {elapsed:.2f}s → {len(emails)} ADMIN(s) trouvé(s)")
            for i, email in enumerate(emails, 1):
                ok(f"  [{i}] {email}")
            result(True, "AuthClient")
            return True, emails
        else:
            warn(f"Réponse reçue en {elapsed:.2f}s → 0 ADMIN trouvé")
            warn("Vérifier : auth-service en ligne ? Des users ADMIN actifs existent ?")
            result(False, "AuthClient — aucun admin")
            return False, []

    except Exception as e:
        elapsed = time.perf_counter() - start
        err(f"Erreur après {elapsed:.2f}s : {e}")
        result(False, "AuthClient")
        return False, []


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Test envoi email avec données fictives
# ══════════════════════════════════════════════════════════════════════════════

def test_email_send(override_emails: list[str] | None = None) -> bool:
    section("STEP 3 — Test envoi email via Resend")

    try:
        import resend
        ok("Import resend OK")
    except ImportError:
        err("Package 'resend' non installé → pip install resend")
        return False

    from app.core.config import settings

    if not settings.RESEND_API_KEY:
        err("RESEND_API_KEY non configuré → email impossible")
        return False

    resend.api_key = settings.RESEND_API_KEY
    ok(f"API Key configurée : {settings.RESEND_API_KEY[:8]}...")

    # Emails destinataires
    if override_emails:
        recipients = override_emails
        info(f"Destinataires (depuis auth-service) : {recipients}")
    else:
        # Fallback : demander manuellement
        email_input = input(
            f"\n  {YELLOW}Entrez un email de test (Enter pour ignorer) : {RESET}"
        ).strip()
        if not email_input:
            warn("Aucun email fourni → test envoi ignoré")
            return True
        recipients = [email_input]

    # Données de test simulées
    fake_counters = {
        "switches_ok":  3,
        "switches_err": 1,
        "rpis_ok":      12,
        "rpis_err":     2,
        "hgws_ok":      8,
        "hgws_err":     1,
    }

    fake_errors = [
        {
            "device_type": "switch",
            "device_ip":   "192.168.1.1",
            "error_type":  "telnet",
            "message":     "[TEST] Connection refused after 3 retries",
        },
        {
            "device_type": "rpi",
            "device_ip":   "10.0.0.42",
            "error_type":  "ssh",
            "message":     "[TEST] Authentication failed for user pi",
        },
        {
            "device_type": "hgw",
            "device_ip":   "AA:BB:CC:DD:EE:FF",
            "error_type":  "ssh",
            "message":     "[TEST] All via RPis failed: timeout",
        },
    ]

    # Construire l'email via EmailService
    try:
        from app.services.email_service import EmailService

        # Monkey-patch get_admin_emails pour ne pas rappeler auth-service
        service = EmailService()
        service.auth_client.get_admin_emails = lambda: recipients

        ok(f"EmailService instancié")
        info(f"Envoi vers : {recipients}")
        info(f"From       : {settings.ALERT_EMAIL_FROM}")

        start = time.perf_counter()
        success = service.send_discovery_report(
            run_id=9999,
            status="partial",
            triggered_by="test_manual_script",
            counters=fake_counters,
            errors=fake_errors,
            elapsed_s=87.34,
        )
        elapsed = time.perf_counter() - start

        if success:
            ok(f"Email envoyé en {elapsed:.2f}s")
            ok(f"Vérifiez la boîte : {recipients}")
        else:
            err(f"Envoi échoué après {elapsed:.2f}s")

        result(success, "Envoi email")
        return success

    except Exception as e:
        err(f"Erreur lors de l'envoi : {e}")
        import traceback
        traceback.print_exc()
        result(False, "Envoi email")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Test full pipeline (simulation complète)
# ══════════════════════════════════════════════════════════════════════════════

def test_full_pipeline() -> bool:
    section("STEP 4 — Simulation pipeline complet")

    info("Simulation : discovery terminée → fetch admins → envoyer rapport")

    # 1. Fetch admins
    try:
        from app.infrastructure.auth_client import AuthClient
        auth_client = AuthClient()
        emails = auth_client.get_admin_emails()
    except Exception as e:
        err(f"AuthClient error : {e}")
        emails = []

    if not emails:
        warn("Aucun admin récupéré depuis auth-service")
        warn("Le pipeline EmailService va skipper l'envoi (comportement normal)")
    else:
        ok(f"{len(emails)} admin(s) : {emails}")

    # 2. Simuler fin de discovery
    fake_run = {
        "run_id":       42,
        "status":       "partial",
        "triggered_by": "scheduler",
        "counters": {
            "switches_ok":  5,
            "switches_err": 0,
            "rpis_ok":      20,
            "rpis_err":     3,
            "hgws_ok":      15,
            "hgws_err":     2,
        },
        "errors": [
            {
                "device_type": "rpi",
                "device_ip":   "10.10.1.55",
                "error_type":  "ssh",
                "message":     "[TEST] Connection timed out",
            },
            {
                "device_type": "hgw",
                "device_ip":   "11:22:33:44:55:66",
                "error_type":  "ba_cli",
                "message":     "[TEST] ba-cli returned no data",
            },
        ],
        "elapsed_s": 123.45,
    }

    info(f"Run simulé  : #{fake_run['run_id']} status={fake_run['status']}")
    info(f"Counters    : {fake_run['counters']}")
    info(f"Errors      : {len(fake_run['errors'])} erreur(s)")

    # 3. EmailService
    try:
        from app.services.email_service import EmailService
        service = EmailService()

        if emails:
            # Override pour utiliser les vrais admins récupérés
            service.auth_client.get_admin_emails = lambda: emails

        start = time.perf_counter()
        success = service.send_discovery_report(**fake_run)
        elapsed = time.perf_counter() - start

        if success:
            ok(f"Pipeline complet OK en {elapsed:.2f}s")
        else:
            warn(f"Pipeline terminé sans envoi (voir logs) en {elapsed:.2f}s")

        result(success or not emails, "Pipeline complet")
        return True

    except Exception as e:
        err(f"Pipeline error : {e}")
        import traceback
        traceback.print_exc()
        result(False, "Pipeline complet")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test manuel du système d'email discovery",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--step",
        choices=["all", "config", "auth", "email", "full"],
        default="all",
        help=(
            "Étape à tester :\n"
            "  config → vérifie les variables d'environnement\n"
            "  auth   → teste la connexion à auth-service\n"
            "  email  → teste l'envoi d'un email via Resend\n"
            "  full   → simule le pipeline complet\n"
            "  all    → toutes les étapes dans l'ordre (défaut)"
        ),
    )
    parser.add_argument(
        "--to",
        type=str,
        default=None,
        help="Email de test pour --step email (ex: --to moi@example.com)",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 55}{RESET}")
    print(f"{BOLD}  🔍 TEST EMAIL — Discovery Service{RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}")

    results: dict[str, bool] = {}
    admin_emails: list[str] = []

    # ── Config ────────────────────────────────────────────────
    if args.step in ("all", "config"):
        results["config"] = test_config()
        if args.step == "config":
            _print_summary(results)
            return

    # ── Auth ─────────────────────────────────────────────────
    if args.step in ("all", "auth"):
        ok_auth, admin_emails = test_auth_client()
        results["auth"] = ok_auth
        if args.step == "auth":
            _print_summary(results)
            return

    # ── Email ─────────────────────────────────────────────────
    if args.step in ("all", "email"):
        override = [args.to] if args.to else (admin_emails or None)
        results["email"] = test_email_send(override_emails=override)
        if args.step == "email":
            _print_summary(results)
            return

    # ── Full ─────────────────────────────────────────────────
    if args.step in ("all", "full"):
        results["full"] = test_full_pipeline()

    _print_summary(results)


def _print_summary(results: dict[str, bool]) -> None:
    section("RÉSUMÉ")
    all_passed = all(results.values())
    for step, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {BOLD}{step:10s}{RESET} → [{status}]")

    print(f"\n{BOLD}{'═' * 55}{RESET}")
    if all_passed:
        print(f"{GREEN}{BOLD}  ✅ Tous les tests passés !{RESET}")
    else:
        failed = [s for s, p in results.items() if not p]
        print(f"{RED}{BOLD}  ❌ Échecs : {', '.join(failed)}{RESET}")
    print(f"{BOLD}{'═' * 55}{RESET}\n")


if __name__ == "__main__":
    main()