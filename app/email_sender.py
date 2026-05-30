"""
Email sender utility — sends access codes via SMTP.

Configure in .env / Render:
  SMTP_HOST     = smtp.gmail.com
  SMTP_PORT     = 587
  SMTP_USER     = you@umd.edu
  SMTP_PASSWORD = 16-char Google app password (no spaces)
  SMTP_FROM     = FrontierOS <you@umd.edu>  (must match SMTP_USER for Gmail)
"""
from __future__ import annotations
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_last_smtp_error: str = ""


def _smtp_config() -> Dict:
    """Read SMTP settings at send time (Render env vars apply correctly)."""
    user = (os.getenv("SMTP_USER", "") or "").strip()
    pwd = (os.getenv("SMTP_PASSWORD", "") or "").replace(" ", "").replace("\n", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    use_ssl = os.getenv("SMTP_USE_SSL", "").lower() in ("1", "true", "yes") or port == 465
    from_hdr = (os.getenv("SMTP_FROM", "") or "").strip()
    if not from_hdr and user:
        from_hdr = formataddr(("FrontierOS", user))
    return {
        "host": (os.getenv("SMTP_HOST", "") or "").strip(),
        "port": port,
        "user": user,
        "password": pwd,
        "from": from_hdr,
        "use_ssl": use_ssl,
    }


def is_email_configured() -> bool:
    c = _smtp_config()
    return bool(c["host"] and c["user"] and c["password"])


def smtp_status() -> Dict:
    """Safe diagnostic payload (no secrets)."""
    c = _smtp_config()
    return {
        "configured": is_email_configured(),
        "host": c["host"],
        "port": c["port"],
        "user": c["user"],
        "password_set": bool(c["password"]),
        "password_length": len(c["password"]),
        "use_ssl": c["use_ssl"],
        "last_error": _last_smtp_error,
    }


def _app_links_enabled() -> bool:
    return os.getenv("EXPOSE_APP", "false").lower() in ("1", "true", "yes")


def send_early_access_code(to_email: str, full_name: str, code: str) -> Tuple[bool, str]:
    """Returns (success, error_message)."""
    if not is_email_configured():
        return False, "SMTP not configured (set SMTP_HOST, SMTP_USER, SMTP_PASSWORD on Render)"
    ok, err = _send_html_email(
        to_email,
        f"Your FrontierOS access code: {code}",
        _early_text(full_name, code),
        _early_html(full_name, code),
    )
    return ok, err


def send_access_code(to_email: str, full_name: str, code: str) -> Tuple[bool, str]:
    if not _app_links_enabled():
        return send_early_access_code(to_email, full_name, code)
    if not is_email_configured():
        return False, "SMTP not configured"
    app_url = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    text = f"""Hi {full_name or 'Researcher'},

Your FrontierOS access code: {code}

Use it at: {app_url}/app
"""
    html = f"""<p>Hi {full_name or 'Researcher'},</p><p>Your code: <b>{code}</b></p>
<p><a href="{app_url}/app?code={code}">Open FrontierOS</a></p>"""
    return _send_html_email(to_email, f"Your FrontierOS access code: {code}", text, html)


def _early_text(full_name: str, code: str) -> str:
    return f"""Hi {full_name or 'Researcher'},

Thanks for signing up for FrontierOS early access.

Your access code: {code}

Save this code. We will notify you when the product launches.

— FrontierOS
"""


def _early_html(full_name: str, code: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;background:#f8f9fa;margin:0;padding:32px;">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:40px;">
  <div style="font-size:22px;font-weight:700;color:#0d1c17;">FrontierOS</div>
  <p style="font-size:16px;color:#1e293b;">Hi {full_name or 'Researcher'},</p>
  <p style="font-size:15px;color:#475569;">Thanks for signing up. Save this access code for launch day.</p>
  <div style="background:#f0fdf8;border:2px solid #14a883;border-radius:12px;padding:28px;text-align:center;margin:28px 0;">
    <div style="font-size:12px;color:#64748b;text-transform:uppercase;">Your access code</div>
    <div style="font-family:monospace;font-size:34px;font-weight:800;color:#14a883;letter-spacing:.2em;">{code}</div>
  </div>
  <p style="font-size:13px;color:#94a3b8;">We will email you when the research terminal is live.</p>
</div>
</body>
</html>
"""


def _connect_smtp(cfg: Dict):
    if cfg["use_ssl"]:
        ctx = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=25, context=ctx)
        return smtp
    smtp = smtplib.SMTP(cfg["host"], cfg["port"], timeout=25)
    smtp.ehlo()
    smtp.starttls(context=ssl.create_default_context())
    smtp.ehlo()
    return smtp


def _send_html_email(to_email: str, subject: str, text: str, html: str) -> Tuple[bool, str]:
    global _last_smtp_error
    cfg = _smtp_config()
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = to_email
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with _connect_smtp(cfg) as smtp:
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(cfg["user"], [to_email], msg.as_string())

        _last_smtp_error = ""
        logger.info("[Email] sent to %s: %s", to_email, subject)
        return True, ""
    except smtplib.SMTPAuthenticationError as exc:
        _last_smtp_error = f"SMTP auth failed: {exc}"
        logger.error("[Email] %s (user=%s)", _last_smtp_error, cfg["user"])
        return False, "Gmail rejected the login — use a Google App Password (not your normal password)."
    except Exception as exc:
        _last_smtp_error = str(exc)
        logger.error("[Email] failed to %s: %s", to_email, exc)
        return False, _last_smtp_error


def send_simple(to: str, subject: str, body: str) -> Tuple[bool, str]:
    if not is_email_configured():
        return False, "SMTP not configured"
    return _send_html_email(to, subject, body, f"<pre>{body}</pre>")
