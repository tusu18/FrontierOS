"""
Email sender — access codes via Resend (HTTPS) or SMTP.

Render **free** tier blocks outbound SMTP (ports 25/465/587). Use either:
  - RESEND_API_KEY + EMAIL_FROM (verified in Resend) — works on free Render
  - SMTP_* — works locally and on paid Render instances

SMTP (.env / Render):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Resend (https://resend.com — free tier):
  RESEND_API_KEY=re_...
  EMAIL_FROM=FrontierOS <you@verified-email.com>
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

import requests

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


def _resend_api_key() -> str:
    return (os.getenv("RESEND_API_KEY", "") or "").strip()


def _email_from() -> str:
    raw = (os.getenv("EMAIL_FROM", "") or os.getenv("SMTP_FROM", "") or "").strip()
    if raw:
        return raw
    user = (os.getenv("SMTP_USER", "") or "").strip()
    return formataddr(("FrontierOS", user)) if user else ""


def is_email_configured() -> bool:
    if _resend_api_key():
        return bool(_email_from())
    c = _smtp_config()
    return bool(c["host"] and c["user"] and c["password"])


def smtp_status() -> Dict:
    """Safe diagnostic payload (no secrets)."""
    c = _smtp_config()
    transport = "resend" if _resend_api_key() else "smtp"
    return {
        "configured": is_email_configured(),
        "transport": transport,
        "render_free_smtp_blocked": (
            "Render free tier blocks SMTP ports 587/465/25 — set RESEND_API_KEY or upgrade the web service."
            if transport == "smtp"
            else None
        ),
        "from": _email_from() or c["from"],
        "host": c["host"],
        "port": c["port"],
        "user": c["user"],
        "password_set": bool(c["password"]),
        "password_length": len(c["password"]),
        "resend_key_set": bool(_resend_api_key()),
        "use_ssl": c["use_ssl"],
        "last_error": _last_smtp_error,
    }


def _app_links_enabled() -> bool:
    return os.getenv("EXPOSE_APP", "false").lower() in ("1", "true", "yes")


def send_early_access_code(to_email: str, full_name: str, code: str) -> Tuple[bool, str]:
    """Returns (success, error_message)."""
    if not is_email_configured():
        return False, (
            "Email not configured — set RESEND_API_KEY + EMAIL_FROM on Render free, "
            "or SMTP_HOST + SMTP_USER + SMTP_PASSWORD on paid/local"
        )
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


def _logo_url() -> str:
    base = (os.getenv("APP_BASE_URL", "") or "").strip().rstrip("/")
    if base:
        return f"{base}/assets/logo-mark.svg"
    return (os.getenv("EMAIL_LOGO_URL", "") or "").strip() or (
        "https://tusu18.github.io/FrontierOS/assets/logo-mark.svg"
    )


def _early_text(full_name: str, code: str) -> str:
    return f"""Hi {full_name or 'Researcher'},

Thanks for signing up for FrontierOS early access.

Know when the frontier moves near your work.

Your access code: {code}

Save this code. We will notify you when the research terminal launches.

— FrontierOS
https://tusu18.github.io/FrontierOS/
"""


def _early_html(full_name: str, code: str) -> str:
    logo = _logo_url()
    name = full_name or "Researcher"
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#f1efe9;margin:0;padding:32px;">
<div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;padding:40px;border:1px solid #e3e0d8;">
  <div style="margin-bottom:24px;">
    <img src="{logo}" alt="FrontierOS" width="36" height="36" style="display:block;margin-bottom:12px;">
    <div style="font-family:system-ui,sans-serif;font-size:22px;font-weight:700;color:#14161a;letter-spacing:-0.02em;">FrontierOS</div>
    <div style="font-size:13px;color:#0b755e;margin-top:4px;">Research Terminal</div>
  </div>
  <p style="font-size:16px;color:#14161a;margin:0 0 8px;">Hi {name},</p>
  <p style="font-size:15px;color:#3d4148;line-height:1.55;margin:0 0 20px;">
    Thanks for signing up for early access. Save this access code for launch day.
  </p>
  <p style="font-size:14px;color:#797f88;font-style:italic;margin:0 0 24px;">
    Know when the frontier moves near your work.
  </p>
  <div style="background:#e9faf3;border:2px solid #14a883;border-radius:12px;padding:28px;text-align:center;margin:0 0 28px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.12em;">Your access code</div>
    <div style="font-family:ui-monospace,monospace;font-size:32px;font-weight:800;color:#0b755e;letter-spacing:0.18em;margin-top:10px;">{code}</div>
  </div>
  <p style="font-size:13px;color:#797f88;line-height:1.5;margin:0;">
    We will email you when the research terminal is live. No dashboard link until then.
  </p>
  <p style="font-size:12px;color:#94a3b8;margin:28px 0 0;border-top:1px solid #e3e0d8;padding-top:20px;">
    — FrontierOS · <a href="https://tusu18.github.io/FrontierOS/" style="color:#0b755e;">tusu18.github.io/FrontierOS</a>
  </p>
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


def _send_via_resend(to_email: str, subject: str, text: str, html: str) -> Tuple[bool, str]:
    global _last_smtp_error
    api_key = _resend_api_key()
    from_addr = _email_from()
    if not api_key:
        return False, "RESEND_API_KEY not set"
    if not from_addr:
        return False, "EMAIL_FROM not set (verify sender in Resend dashboard)"
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_addr,
                "to": [to_email],
                "subject": subject,
                "text": text,
                "html": html,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            _last_smtp_error = ""
            logger.info("[Email/Resend] sent to %s: %s", to_email, subject)
            return True, ""
        detail = resp.text[:500]
        try:
            detail = resp.json().get("message", detail)
        except Exception:
            pass
        _last_smtp_error = f"Resend HTTP {resp.status_code}: {detail}"
        logger.error("[Email/Resend] %s", _last_smtp_error)
        return False, _last_smtp_error
    except Exception as exc:
        _last_smtp_error = str(exc)
        logger.error("[Email/Resend] failed to %s: %s", to_email, exc)
        return False, _last_smtp_error


def _send_html_email(to_email: str, subject: str, text: str, html: str) -> Tuple[bool, str]:
    global _last_smtp_error
    if _resend_api_key():
        return _send_via_resend(to_email, subject, text, html)
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
    except OSError as exc:
        err = str(exc)
        if "unreachable" in err.lower() or getattr(exc, "errno", None) == 101:
            _last_smtp_error = err
            msg = (
                "SMTP blocked on Render free tier (ports 587/465). "
                "Add RESEND_API_KEY in Render, or set up EmailJS on the landing page — see DEPLOY.md."
            )
            logger.error("[Email] %s", msg)
            return False, msg
        _last_smtp_error = err
        logger.error("[Email] failed to %s: %s", to_email, exc)
        return False, err
    except Exception as exc:
        _last_smtp_error = str(exc)
        logger.error("[Email] failed to %s: %s", to_email, exc)
        return False, _last_smtp_error


def send_simple(to: str, subject: str, body: str) -> Tuple[bool, str]:
    if not is_email_configured():
        return False, "SMTP not configured"
    return _send_html_email(to, subject, body, f"<pre>{body}</pre>")
