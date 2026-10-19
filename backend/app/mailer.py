"""Plain-text email through the company mail server (SMTP_* settings). Used to tell admins about access requests.

Sending is best-effort and runs in the background: a mail server that is down or refuses never affects the portal,
it is only logged. Without SMTP_HOST nothing is sent."""

import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("uam.mail")
TIMEOUT_SECONDS = 15


def mail_configured() -> bool:
    return bool(settings.smtp_host.strip())


def send_mail(to: list[str], subject: str, body: str) -> bool:
    if not mail_configured() or not to:
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or f"Access Portal <{settings.smtp_user}>"
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SECONDS) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - never let the mail server affect the portal
        log.warning("Email '%s' to %s failed: %s", subject, ", ".join(to), exc)
        return False
