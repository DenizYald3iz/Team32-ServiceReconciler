from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .settings import settings


def send_email(subject: str, body: str) -> bool:
    """Send an email if SMTP settings are configured.

    Environment variables:
      - DSR_ENABLE_EMAIL=true
      - DSR_SMTP_HOST / DSR_SMTP_PORT
      - DSR_SMTP_USER / DSR_SMTP_PASSWORD
      - DSR_EMAIL_FROM / DSR_EMAIL_TO
    """
    if not settings.enable_email:
        return False
    if not all(
        [
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.email_from,
            settings.email_to,
        ]
    ):
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.email_from
        msg["To"] = settings.email_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.email_from, [settings.email_to], msg.as_string())
        server.quit()
        return True
    except Exception:
        return False
