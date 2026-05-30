"""
Fetch daily papers from arXiv, summarize them, and analyze trends.
Run this manually or via the scheduler.
"""

import sys
import os
import argparse
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

from app.database import create_all_tables
from app.openrouter_client import is_api_key_configured

logger = logging.getLogger(__name__)


def main(summarize: bool = True, analyze_trends: bool = True, max_results: int = None):
    create_all_tables()

    # Step 1: Collect papers
    logger.info("Step 1: Collecting papers from arXiv...")
    from app.agents.paper_collector_agent import PaperCollectorAgent
    collector = PaperCollectorAgent()
    if max_results:
        collector.max_results = max_results
    papers = collector.run()
    print(f"✅ Collected {len(papers)} papers")

    if not papers:
        print("⚠️  No papers collected. Check your internet connection and try again.")
        return

    # Step 2: Summarize (requires API key)
    if summarize:
        if not is_api_key_configured():
            print("⚠️  OPENROUTER_API_KEY not set — skipping summarization.")
            print("    Add your API key to .env and re-run to summarize papers.")
        else:
            logger.info("Step 2: Summarizing papers with OpenRouter...")
            from app.agents.paper_summarizer_agent import PaperSummarizerAgent
            from tqdm import tqdm

            paper_ids = [p.get("db_id") for p in papers if p.get("db_id")]
            agent = PaperSummarizerAgent(skip_existing=True)

            # Progress bar
            pbar = tqdm(total=len(paper_ids), desc="Summarizing", unit="paper")

            def progress_cb(done, total):
                pbar.n = done
                pbar.refresh()

            results = agent.run(paper_ids=paper_ids, progress_callback=progress_cb)
            pbar.close()
            print(f"✅ Summarized {len(results)} papers")

    # Step 3: Trend analysis
    if analyze_trends:
        if not is_api_key_configured():
            print("⚠️  OPENROUTER_API_KEY not set — skipping trend analysis.")
        else:
            logger.info("Step 3: Running trend analysis...")
            from app.agents.trend_analyst_agent import TrendAnalystAgent
            agent = TrendAnalystAgent()
            trend = agent.run(save=True)
            if trend:
                print("✅ Trend analysis complete")
                print(f"   Dominant themes: {', '.join(trend.get('dominant_themes', [])[:3])}")
            else:
                print("⚠️  Trend analysis returned no results")

    # Step 4: Knowledge Graph ingestion (rule-based, no API key needed for basic extraction)
    logger.info("Step 4: Updating research knowledge graph…")
    from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
    kg_agent = KnowledgeGraphBuilderAgent()
    kg_results = kg_agent.run(limit=len(papers))
    print(f"✅ KG updated — {len(kg_results)} papers ingested into research memory")

    # Step 5: Research gap scan
    logger.info("Step 5: Scanning research gaps…")
    from app.agents.research_gap_memory_agent import ResearchGapMemoryAgent
    gap_agent = ResearchGapMemoryAgent()
    gaps = gap_agent.run(limit=30)
    if gaps:
        print(f"✅ Research gaps scanned — {len(gaps)} active gaps tracked")

    print("\n🎉 Daily fetch complete!")
    print("   Run: streamlit run app/dashboard.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch daily arXiv papers")
    parser.add_argument("--no-summarize", action="store_true", help="Skip LLM summarization")
    parser.add_argument("--no-trends", action="store_true", help="Skip trend analysis")
    parser.add_argument("--max-results", type=int, default=None, help="Override max results")
    args = parser.parse_args()

    main(
        summarize=not args.no_summarize,
        analyze_trends=not args.no_trends,
        max_results=args.max_results,
    )
