"""
Service d'envoi d'email via Resend.
- Récupère les emails ADMIN depuis auth-service
- Envoie un rapport HTML après chaque discovery
- Jamais bloquant : toutes les erreurs sont loggées
"""

import resend
from datetime import datetime

from app.core.config import settings
from app.core.logger import get_logger
from app.infrastructure.auth_client import AuthClient

logger = get_logger(__name__)


class EmailService:
    def __init__(self):
        resend.api_key = settings.RESEND_API_KEY
        self.auth_client = AuthClient()

    # ==========================================================
    # PUBLIC
    # ==========================================================
    def send_discovery_report(
        self,
        run_id: int,
        status: str,
        triggered_by: str,
        counters: dict,
        errors: list,
        elapsed_s: float,
    ) -> bool:
        """
        Envoie le rapport discovery aux admins.
        Retourne True si succès.
        """

        if not settings.RESEND_API_KEY:
            logger.warning(
                "[EMAIL] RESEND_API_KEY not set",
                extra={"run_id": run_id}
            )
            return False

        admin_emails = self.auth_client.get_admin_emails()

        if not admin_emails:
            logger.warning(
                "[EMAIL] No active ADMIN found",
                extra={"run_id": run_id}
            )
            return False

        total_errors = (
            counters.get("switches_err", 0)
            + counters.get("rpis_err", 0)
            + counters.get("hgws_err", 0)
        )

        if total_errors == 0 and status == "done":
            logger.info(
                "[EMAIL] No errors, skipping email",
                extra={"run_id": run_id}
            )
            return True

        subject = self._build_subject(
            run_id,
            status,
            total_errors
        )

        html_body = self._build_html(
            run_id,
            status,
            triggered_by,
            counters,
            errors,
            elapsed_s,
            total_errors
        )

        text_body = self._build_text(
            run_id,
            status,
            triggered_by,
            counters,
            errors,
            elapsed_s,
            total_errors
        )

        try:
            response = resend.Emails.send({
                "from": settings.ALERT_EMAIL_FROM,
                "to": admin_emails,
                "subject": subject,
                "html": html_body,
                "text": text_body,
            })

            logger.info(
                "[EMAIL] ✓ Report sent (resend_id=%s)",
                response.get("id"),
                extra={
                    "run_id": run_id,
                    "resend_id": response.get("id"),
                    "recipients": len(admin_emails),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "[EMAIL] Failed to send report: %s",
                e,
                exc_info=True,
                extra={"run_id": run_id},
            )
            return False

    # ==========================================================
    # SUBJECT
    # ==========================================================
    def _build_subject(
        self,
        run_id: int,
        status: str,
        total_errors: int
    ) -> str:

        icon = {
            "done": "✅",
            "partial": "⚠️",
            "error": "❌"
        }.get(status, "ℹ️")

        return (
            f"{icon} Discovery #{run_id} "
            f"| {status.upper()} "
            f"| {total_errors} erreur(s)"
        )

    # ==========================================================
    # TEXT VERSION
    # ==========================================================
    def _build_text(
        self,
        run_id,
        status,
        triggered_by,
        counters,
        errors,
        elapsed_s,
        total_errors,
    ):

        lines = [
            "=" * 50,
            f"DISCOVERY REPORT #{run_id}",
            "=" * 50,
            f"Date      : {datetime.utcnow()} UTC",
            f"Status    : {status.upper()}",
            f"Triggered : {triggered_by}",
            f"Duration  : {elapsed_s:.1f}s",
            "",
            "Counters:",
            f"Switches : {counters.get('switches_ok',0)} OK / {counters.get('switches_err',0)} ERR",
            f"RPis     : {counters.get('rpis_ok',0)} OK / {counters.get('rpis_err',0)} ERR",
            f"HGWs     : {counters.get('hgws_ok',0)} OK / {counters.get('hgws_err',0)} ERR",
            f"TOTAL ERRORS: {total_errors}",
            "",
        ]

        if errors:
            lines.append("Errors:")
            for err in errors:
                lines.append(
                    f"[{getattr(err,'device_type','?').upper():8s}] "
                    f"{getattr(err,'device_ip','?'):20s} "
                    f"({getattr(err,'stage','?')}) "
                    f"→ {getattr(err,'error','?')}"
                )
        else:
            lines.append("No errors detected.")

        return "\n".join(lines)

    # ==========================================================
    # HTML VERSION
    # ==========================================================
    def _build_html(
        self,
        run_id,
        status,
        triggered_by,
        counters,
        errors,
        elapsed_s,
        total_errors,
    ):

        color = {
            "done": "#10b981",
            "partial": "#f59e0b",
            "error": "#ef4444"
        }.get(status, "#64748b")

        rows_html = ""

        for err in errors:
            rows_html += f"""
            <tr>
                <td>{getattr(err,'device_type','?').upper()}</td>
                <td>{getattr(err,'device_ip','?')}</td>
                <td>{getattr(err,'stage','?')}</td>
                <td>{getattr(err,'error','?')}</td>
            </tr>
            """

        if not rows_html:
            rows_html = """
            <tr>
                <td colspan="4">
                    No errors detected
                </td>
            </tr>
            """

        return f"""
        <html>
        <body style="font-family:Arial,sans-serif;
                     background:#f8fafc;
                     padding:30px;">

            <div style="
                max-width:700px;
                margin:auto;
                background:white;
                padding:30px;
                border-radius:10px;
                border-top:6px solid {color};
            ">

                <h2>
                    Discovery Report #{run_id}
                </h2>

                <p>
                    <b>Status:</b> {status.upper()}<br>
                    <b>Triggered by:</b> {triggered_by}<br>
                    <b>Duration:</b> {elapsed_s:.1f}s<br>
                    <b>Total errors:</b> {total_errors}
                </p>

                <h3>Infrastructure Summary</h3>

                <ul>
                    <li>
                        Switches:
                        {counters.get('switches_ok',0)}
                        OK /
                        {counters.get('switches_err',0)}
                        ERR
                    </li>

                    <li>
                        RPis:
                        {counters.get('rpis_ok',0)}
                        OK /
                        {counters.get('rpis_err',0)}
                        ERR
                    </li>

                    <li>
                        HGWs:
                        {counters.get('hgws_ok',0)}
                        OK /
                        {counters.get('hgws_err',0)}
                        ERR
                    </li>
                </ul>

                <h3>Error Details</h3>

                <table
                    border="1"
                    cellpadding="8"
                    cellspacing="0"
                    width="100%"
                    style="border-collapse:collapse;"
                >
                    <tr style="background:#f1f5f9;">
                        <th>Type</th>
                        <th>Device IP</th>
                        <th>Stage</th>
                        <th>Error</th>
                    </tr>

                    {rows_html}

                </table>

                <p style="
                    margin-top:30px;
                    color:gray;
                    font-size:12px;
                ">
                    Automatic report generated by
                    Network Discovery System
                </p>

            </div>
        </body>
        </html>
        """