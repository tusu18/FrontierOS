#!/usr/bin/env python3
"""test_alert_rules.py — verify default alert rules are created and AlertAgent runs."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils import load_env  # noqa: E402
load_env()


def main():
    from app.database import (
        get_session, create_all_tables, create_user, get_user_by_email,
        ensure_default_alert_rules_for_user, AlertRule,
    )
    from app.auth import hash_password
    create_all_tables()
    s = get_session()
    ok = True
    try:
        email = "alertrule_test@example.com"
        u = get_user_by_email(s, email)
        if not u:
            u = create_user(s, email, hash_password("x"), "Alert Test")
            s.commit()

        # Clear any existing rules for a clean test
        s.query(AlertRule).filter_by(user_id=u.id).delete()
        s.commit()

        created = ensure_default_alert_rules_for_user(s, u.id)
        s.commit()
        count = s.query(AlertRule).filter_by(user_id=u.id).count()
        ok = created > 0 and count == created
        print(f"[{'PASS' if ok else 'FAIL'}] default rules created: {created} (total {count})")

        # AlertAgent should run without crashing
        from app.agents.alert_agent import AlertAgent
        res = AlertAgent().run(user_ids=[u.id])
        print(f"[PASS] AlertAgent ran: {res}")
    except Exception as e:
        ok = False
        print(f"[FAIL] {e}")
    finally:
        s.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
