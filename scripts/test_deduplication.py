#!/usr/bin/env python3
"""test_deduplication.py — verify a duplicate arxiv_id is not inserted twice."""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils import load_env  # noqa: E402
load_env()


def main():
    from app.database import get_session, create_all_tables, upsert_paper, Paper
    create_all_tables()
    s = get_session()
    ok = True
    try:
        test_id = "9999.00001v1"
        meta = {
            "arxiv_id": test_id, "title": "Dedup Test Paper",
            "authors": ["Test"], "abstract": "x", "categories": ["cs.AI"],
            "primary_category": "cs.AI", "published_date": "2026-01-01",
            "pdf_url": "", "arxiv_url": "",
        }
        p1 = upsert_paper(s, meta); s.commit()
        p2 = upsert_paper(s, meta); s.commit()

        count = s.query(Paper).filter_by(arxiv_id=test_id).count()
        ok = (p1.id == p2.id) and (count == 1)
        print(f"[{'PASS' if ok else 'FAIL'}] duplicate arxiv_id not inserted twice "
              f"(id1={p1.id}, id2={p2.id}, rows={count})")

        # cleanup
        s.query(Paper).filter_by(arxiv_id=test_id).delete()
        s.commit()
    finally:
        s.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
