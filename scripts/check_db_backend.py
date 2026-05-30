#!/usr/bin/env python3
"""check_db_backend.py — report the active database backend and connectivity."""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils import load_env  # noqa: E402
load_env()


def main():
    db_url = os.getenv("DATABASE_URL", "sqlite:///data/arxiv_papers.db")
    kind = "postgres" if db_url.startswith("postgres") else "sqlite" if db_url.startswith("sqlite") else "other"
    print(f"DATABASE_URL: {db_url}")
    print(f"Backend:      {kind}")

    from sqlalchemy import create_engine, inspect, text
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        insp = inspect(engine)
        tables = insp.get_table_names()
        print(f"Connection:   OK")
        print(f"Tables:       {len(tables)}")
        for t in sorted(tables):
            print(f"  - {t}")
    except Exception as e:
        print(f"Connection:   FAILED — {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
