"""
Entry point: launches the ResearchRadar FastAPI server.

Usage:
  python run.py               # http://localhost:8000
  python run.py --port 8080
  python run.py --reload      # auto-reload on code changes (dev mode)
"""

import os
import sys
import argparse

# Ensure CWD is the project root so all relative imports work.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass

from app.utils import load_env, ensure_dirs
load_env()
ensure_dirs()

from app.database import create_all_tables
create_all_tables()

parser = argparse.ArgumentParser(description="ResearchRadar server")
parser.add_argument("--port",   type=int, default=8000)
parser.add_argument("--host",   default="0.0.0.0")
parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
args = parser.parse_args()

print("=" * 56)
print("  FrontierOS — Research Intelligence Terminal")
print("=" * 56)
print(f"  Dashboard  →  http://localhost:{args.port}/app")
print(f"  Landing    →  http://localhost:{args.port}/")
print(f"  API docs   →  http://localhost:{args.port}/api/docs")
print("=" * 56)
print("  Press Ctrl+C to stop.")

import uvicorn
uvicorn.run(
    "app.api.server:app",
    host=args.host,
    port=args.port,
    reload=args.reload,
    log_level="info",
)
