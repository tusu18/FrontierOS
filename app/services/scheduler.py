"""APScheduler-based daily paper fetching and summarization."""

from __future__ import annotations
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def daily_job():
    """The daily job: fetch papers, summarize, analyze trends."""
    logger.info(f"[Scheduler] Daily job started at {datetime.now()}")
    try:
        from app.agents.paper_collector_agent import PaperCollectorAgent
        from app.agents.paper_summarizer_agent import PaperSummarizerAgent
        from app.agents.trend_analyst_agent import TrendAnalystAgent

        collector = PaperCollectorAgent()
        papers = collector.run()
        logger.info(f"[Scheduler] Collected {len(papers)} papers")

        if papers:
            summarizer = PaperSummarizerAgent(skip_existing=True)
            paper_ids = [p.get("db_id") for p in papers if p.get("db_id")]
            summarizer.run(paper_ids=paper_ids)
            logger.info("[Scheduler] Summarization done")

            analyst = TrendAnalystAgent()
            analyst.run(save=True)
            logger.info("[Scheduler] Trend analysis done")

    except Exception as e:
        logger.error(f"[Scheduler] Daily job failed: {e}")
    logger.info(f"[Scheduler] Daily job finished at {datetime.now()}")


def start_scheduler():
    """Start APScheduler with daily job at configured time."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return None

    scheduler = BackgroundScheduler()
    # Default: 6 AM UTC daily
    hour = int(os.getenv("SCHEDULER_HOUR", "6"))
    minute = int(os.getenv("SCHEDULER_MINUTE", "0"))

    scheduler.add_job(
        daily_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_paper_fetch",
        replace_existing=True,
        name="Daily arXiv Paper Fetch",
    )
    scheduler.start()
    logger.info(f"[Scheduler] Started. Daily job at {hour:02d}:{minute:02d} UTC")
    return scheduler


def stop_scheduler(scheduler):
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
