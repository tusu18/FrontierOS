"""
Backfill: fetch papers for a date range and summarize all unsummarized papers.
Useful when setting up for the first time or recovering from missed days.
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

from app.database import create_all_tables
from app.openrouter_client import is_api_key_configured


def main(total_papers: int = 200, summarize: bool = True):
    create_all_tables()

    print(f"Backfilling {total_papers} papers from arXiv...")
    from app.agents.paper_collector_agent import PaperCollectorAgent
    agent = PaperCollectorAgent(max_results=total_papers)
    papers = agent.run()
    print(f"✅ Collected {len(papers)} papers")

    if summarize and is_api_key_configured():
        print("Summarizing all unsummarized papers...")
        from app.agents.paper_summarizer_agent import PaperSummarizerAgent
        from tqdm import tqdm

        summarizer = PaperSummarizerAgent(skip_existing=True)
        pbar = tqdm(total=1, desc="Summarizing")

        def cb(done, total):
            pbar.total = total
            pbar.n = done
            pbar.refresh()

        results = summarizer.run(progress_callback=cb)
        pbar.close()
        print(f"✅ Summarized {len(results)} papers")
    elif not is_api_key_configured():
        print("⚠️  Set OPENROUTER_API_KEY to enable summarization.")

    print("✅ Backfill complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--papers", type=int, default=200)
    parser.add_argument("--no-summarize", action="store_true")
    args = parser.parse_args()
    main(total_papers=args.papers, summarize=not args.no_summarize)
