"""
Run the APScheduler background scheduler.
This process runs continuously and executes the daily fetch job.
Keep it running in a terminal or configure as a system service.
"""

import sys
import os
import time
import signal
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

from app.database import create_all_tables
from app.services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

scheduler = None


def handle_exit(signum, frame):
    print("\n🛑 Shutting down scheduler...")
    stop_scheduler(scheduler)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    create_all_tables()
    hour = int(os.getenv("SCHEDULER_HOUR", "6"))
    minute = int(os.getenv("SCHEDULER_MINUTE", "0"))

    print(f"⏰ Starting scheduler — daily job at {hour:02d}:{minute:02d} UTC")
    print("   Press Ctrl+C to stop.")

    scheduler = start_scheduler()
    if scheduler:
        while True:
            time.sleep(60)
    else:
        print("❌ Failed to start scheduler. Install: pip install apscheduler")
