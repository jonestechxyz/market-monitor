"""
Sends the briefing via Gmail SMTP.
Credentials are read from environment variables:
  GMAIL_USER     – sender Gmail address
  GMAIL_APP_PASS – Gmail App Password (not account password)
  BRIEFING_TO    – comma-separated recipient addresses
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_briefing(subject: str, body_text: str, body_html: str = "") -> bool:
    """Send the briefing email with HTML body. Returns True on success."""
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASS", "").strip()
    recipients_raw = os.environ.get("BRIEFING_TO", "").strip()

    if not gmail_user or not gmail_pass:
        logger.warning("GMAIL_USER / GMAIL_APP_PASS not set — skipping email.")
        return False
    if not recipients_raw:
        logger.warning("BRIEFING_TO not set — skipping email.")
        return False

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = ", ".join(recipients)

    # plain text fallback
    msg.attach(MIMEText(body_text, "plain"))

    # HTML body — full magazine layout
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=30) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, recipients, msg.as_string())
        logger.info("Briefing emailed to %s", recipients)
        return True
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return False
