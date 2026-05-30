"""Initialize the SQLite database."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

from app.database import create_all_tables, get_db_url

if __name__ == "__main__":
    print(f"Initializing database at: {get_db_url()}")
    create_all_tables()
    print("✅ Database initialized successfully.")
    print("\nNext steps:")
    print("  python scripts/fetch_daily.py    # Fetch 50 arXiv papers")
    print("  streamlit run app/dashboard.py  # Launch dashboard")
