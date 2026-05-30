"""
Email sender utility — sends access codes via SMTP.

Configure in .env:
  SMTP_HOST     = smtp.gmail.com
  SMTP_PORT     = 587
  SMTP_USER     = you@gmail.com
  SMTP_PASSWORD = your_app_password
  SMTP_FROM     = FrontierOS <you@gmail.com>
"""
from __future__ import annotations
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", f"FrontierOS <{SMTP_USER}>")


def is_email_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_access_code(to_email: str, full_name: str, code: str) -> bool:
    """
    Send a demo access code email. Returns True if sent, False if SMTP not configured.
    """
    if not is_email_configured():
        logger.info("[Email] SMTP not configured — code %s for %s logged only", code, to_email)
        return False

    app_url = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;background:#f8f9fa;margin:0;padding:32px;">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:40px;box-shadow:0 4px 24px rgba(0,0,0,.08);">
  <div style="font-size:22px;font-weight:700;color:#0d1c17;margin-bottom:8px;">FrontierOS</div>
  <div style="font-size:13px;color:#64748b;margin-bottom:32px;border-bottom:1px solid #f1f5f9;padding-bottom:16px;">Research Intelligence Terminal</div>

  <p style="font-size:16px;color:#1e293b;line-height:1.6;">Hi {full_name or 'Researcher'},</p>
  <p style="font-size:15px;color:#475569;line-height:1.6;">Your FrontierOS access code is ready. Use it to log into the research terminal — no password needed.</p>

  <div style="background:#f0fdf8;border:2px solid #14a883;border-radius:12px;padding:28px;text-align:center;margin:28px 0;">
    <div style="font-size:12px;color:#64748b;letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px;">Your Access Code</div>
    <div style="font-family:monospace;font-size:34px;font-weight:800;color:#14a883;letter-spacing:.2em;">{code}</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:10px;">Keep this code safe — it never expires</div>
  </div>

  <a href="{app_url}/app?code={code}" style="display:block;background:#14a883;color:#fff;text-align:center;padding:14px 24px;border-radius:10px;text-decoration:none;font-size:15px;font-weight:600;margin-bottom:20px;">
    Enter FrontierOS →
  </a>

  <p style="font-size:13px;color:#94a3b8;line-height:1.6;">
    Or go to <a href="{app_url}/app" style="color:#14a883;">{app_url}/app</a>, open the Access code tab, and enter <strong style="font-family:monospace;">{code}</strong>.
  </p>

  <hr style="border:none;border-top:1px solid #f1f5f9;margin:24px 0;">
  <p style="font-size:12px;color:#cbd5e1;">FrontierOS · CS research intelligence · <a href="{app_url}" style="color:#14a883;">{app_url}</a></p>
</div>
</body>
</html>
"""

    text = f"""Hi {full_name or 'Researcher'},

Your FrontierOS access code: {code}

Use it at: {app_url}/app
Open the Access code tab and enter: {code}

ResearchRadar — AI-powered CS research intelligence
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your ResearchRadar Access Code: {code}"
        msg["From"]    = SMTP_FROM
        msg["To"]      = to_email
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(SMTP_USER, [to_email], msg.as_string())

        logger.info("[Email] access code sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("[Email] failed to send to %s: %s", to_email, exc)
        return False
