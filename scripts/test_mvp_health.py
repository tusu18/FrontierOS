#!/usr/bin/env python3
"""test_mvp_health.py — sanity checks that the MVP is wired correctly."""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils import load_env  # noqa: E402
load_env()

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
results = []


def check(name, cond, level_if_false=FAIL, detail=""):
    status = PASS if cond else level_if_false
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def main():
    from app.database import (
        get_session, create_all_tables, Paper, Summary, KGEntity, User,
    )
    create_all_tables()
    s = get_session()
    try:
        check("DB connects", True)
        check("At least 1 paper exists", s.query(Paper).count() > 0, WARN,
              f"{s.query(Paper).count()} papers")
        check("Summaries table accessible", s.query(Summary).count() >= 0)
        check("KG entities table accessible", s.query(KGEntity).count() >= 0,
              detail=f"{s.query(KGEntity).count()} entities")
        check("Users table accessible", s.query(User).count() >= 0)
        admin = s.query(User).filter_by(is_admin=True).first()
        check("Admin user exists", admin is not None, WARN,
              admin.email if admin else "no admin")

        key_set = bool(os.getenv("OPENROUTER_API_KEY"))
        check("OPENROUTER_API_KEY set", key_set, WARN)
        if key_set:
            try:
                from app.openrouter_client import call_openrouter
                probe = call_openrouter([{"role": "user", "content": "OK"}], max_tokens=4)
                check("OpenRouter API reachable", bool(probe and str(probe).strip()), WARN,
                      "empty response — check key credits or 403 Forbidden")
            except Exception as e:
                check("OpenRouter API reachable", False, WARN, str(e)[:80])

        from app.email_sender import is_email_configured
        check("SMTP configured", is_email_configured(), WARN,
              "code shown in UI when missing")

        backend = os.getenv("MEMORY_BACKEND", "local")
        check("Memory backend known", backend in ("local", "qdrant", "disabled"),
              detail=backend)
    finally:
        s.close()

    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results)} checks, {len(failed)} failures.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
