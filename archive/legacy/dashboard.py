"""
Arxiv CS Agentic Research Dashboard
Main Streamlit application — 8 tabs.
"""

from __future__ import annotations
import json
import logging
import os
import sys

# Add project root to path so `app` imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from collections import Counter
from datetime import date

from app.database import (
    create_all_tables, get_session, get_papers_with_summaries,
    get_all_keywords, get_all_trend_tags, get_stats, paper_to_dict, Paper, Summary
)
from app.openrouter_client import is_api_key_configured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ArXiv CS Research Dashboard",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Init DB on first run
# ---------------------------------------------------------------------------
create_all_tables()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🔬 ArXiv CS Dashboard")
    st.markdown("---")

    api_ok = is_api_key_configured()
    if api_ok:
        st.success("✅ OpenRouter API key detected")
    else:
        st.error("❌ No API key. Add OPENROUTER_API_KEY to .env")

    st.markdown("---")
    st.markdown("**Quick Actions**")

    if st.button("🔄 Fetch Papers Now", use_container_width=True):
        with st.spinner("Fetching papers from arXiv..."):
            from app.agents.paper_collector_agent import PaperCollectorAgent
            agent = PaperCollectorAgent()
            papers = agent.run()
            st.success(f"Fetched {len(papers)} papers!")
            st.rerun()

    if st.button("🤖 Summarize Unsummarized", use_container_width=True, disabled=not api_ok):
        with st.spinner("Summarizing papers..."):
            from app.agents.paper_summarizer_agent import PaperSummarizerAgent
            agent = PaperSummarizerAgent(skip_existing=True)
            results = agent.run()
            st.success(f"Summarized {len(results)} papers!")
            st.rerun()

    if st.button("📊 Analyze Trends", use_container_width=True, disabled=not api_ok):
        with st.spinner("Analyzing trends..."):
            from app.agents.trend_analyst_agent import TrendAnalystAgent
            agent = TrendAnalystAgent()
            result = agent.run()
            if result:
                st.success("Trend analysis complete!")
            else:
                st.error("Trend analysis failed.")
            st.rerun()

    if st.button("🧠 Build Knowledge Graph", use_container_width=True, disabled=not api_ok):
        with st.spinner("Extracting entities & relationships…"):
            from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
            agent = KnowledgeGraphBuilderAgent()
            results = agent.run(limit=10)
            st.success(f"KG updated — {len(results)} papers processed!")
            st.rerun()

    st.markdown("---")
    session = get_session()
    try:
        stats = get_stats(session)
        from app.database import get_kg_stats
        kg_stats_sidebar = get_kg_stats(session)
    finally:
        session.close()

    st.metric("Total Papers", stats["total"])
    st.metric("Summarized", stats["summarized"])
    st.metric("Papers Fetched Today", stats["today"])
    st.markdown("---")
    st.caption("**Knowledge Graph**")
    st.metric("KG Entities", kg_stats_sidebar.get("entities", 0))
    st.metric("KG Relationships", kg_stats_sidebar.get("edges", 0))

# ---------------------------------------------------------------------------
# Tab definitions
# ---------------------------------------------------------------------------
tabs = st.tabs([
    "📊 Overview",
    "📄 Daily Papers",
    "🔍 Deep Analysis",
    "📈 Trend Analytics",
    "🤖 Agentic Tools",
    "💻 Generate Code",
    "📝 Research Reports",
    "🧠 Knowledge Graph",
    "🔮 Memory Search",
    "⚙️ Settings",
])

# ---------------------------------------------------------------------------
# Helper: Load all papers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120)
def load_papers(limit=300):
    session = get_session()
    try:
        return get_papers_with_summaries(session, limit=limit)
    finally:
        session.close()


@st.cache_data(ttl=120)
def load_keywords():
    session = get_session()
    try:
        return get_all_keywords(session)
    finally:
        session.close()


@st.cache_data(ttl=120)
def load_trend_tags():
    session = get_session()
    try:
        return get_all_trend_tags(session)
    finally:
        session.close()


# ============================================================
# TAB 1: Overview
# ============================================================
with tabs[0]:
    st.header("📊 Overview")

    papers = load_papers()

    if not papers:
        st.info("No papers in database yet. Click **Fetch Papers Now** in the sidebar to get started.")
    else:
        # --- Top metrics row ---
        col1, col2, col3, col4, col5 = st.columns(5)

        novelty_vals = [p.get("novelty_score", 5) for p in papers if p.get("novelty_score")]
        impact_vals = [p.get("impact_score", 5) for p in papers if p.get("impact_score")]
        avg_novelty = round(sum(novelty_vals) / len(novelty_vals), 1) if novelty_vals else 0
        avg_impact = round(sum(impact_vals) / len(impact_vals), 1) if impact_vals else 0

        col1.metric("📄 Total Papers", len(papers))
        col2.metric("✅ Summarized", sum(1 for p in papers if p.get("one_line_summary")))
        col3.metric("🗂️ Categories", len(set(p.get("primary_category", "") for p in papers)))
        col4.metric("⭐ Avg Novelty", f"{avg_novelty}/10")
        col5.metric("💥 Avg Impact", f"{avg_impact}/10")

        st.markdown("---")

        # --- Charts row 1 ---
        col_l, col_r = st.columns(2)

        with col_l:
            # Papers by category
            cat_counts = Counter(p.get("primary_category", "unknown") for p in papers)
            df_cat = pd.DataFrame(cat_counts.most_common(15), columns=["Category", "Count"])
            fig = px.bar(df_cat, x="Count", y="Category", orientation="h",
                         title="Papers by Category", color="Count",
                         color_continuous_scale="Blues")
            fig.update_layout(height=400, showlegend=False, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            # Top keywords
            kw_data = load_keywords()
            if kw_data:
                kw_counts = Counter(d["keyword"] for d in kw_data)
                df_kw = pd.DataFrame(kw_counts.most_common(20), columns=["Keyword", "Count"])
                fig = px.bar(df_kw, x="Keyword", y="Count", title="Top Keywords",
                             color="Count", color_continuous_scale="Greens")
                fig.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Summarize papers to see keyword trends.")

        # --- Charts row 2 ---
        col_l2, col_r2 = st.columns(2)

        with col_l2:
            # Top trend tags
            tag_data = load_trend_tags()
            if tag_data:
                tag_counts = Counter(d["tag"] for d in tag_data)
                df_tags = pd.DataFrame(tag_counts.most_common(20), columns=["Tag", "Count"])
                fig = px.bar(df_tags, x="Tag", y="Count", title="Top Trend Tags",
                             color="Count", color_continuous_scale="Oranges")
                fig.update_layout(height=350, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Summarize papers to see trend tags.")

        with col_r2:
            # Novelty vs Impact scatter
            df_scores = pd.DataFrame([{
                "title": p.get("title", "")[:40],
                "novelty": p.get("novelty_score", 5),
                "impact": p.get("impact_score", 5),
                "category": p.get("primary_category", ""),
                "area": p.get("research_area", ""),
            } for p in papers if p.get("novelty_score") and p.get("impact_score")])

            if not df_scores.empty:
                fig = px.scatter(
                    df_scores, x="novelty", y="impact",
                    color="category", hover_name="title",
                    title="Novelty vs Impact",
                    labels={"novelty": "Novelty Score", "impact": "Impact Score"},
                    size_max=10,
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

        # --- Papers over time ---
        date_counts = Counter(p.get("published_date", "")[:7] for p in papers if p.get("published_date"))
        if date_counts:
            df_time = pd.DataFrame(sorted(date_counts.items()), columns=["Month", "Papers"])
            fig = px.line(df_time, x="Month", y="Papers", title="Papers Collected Over Time",
                          markers=True)
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        # --- Where Research Is Going ---
        st.markdown("---")
        st.subheader("🚀 Where Research Is Going")

        session = get_session()
        try:
            from app.database import DailyTrend
            latest_trend = session.query(DailyTrend).order_by(DailyTrend.created_at.desc()).first()
        finally:
            session.close()

        if latest_trend:
            try:
                td = json.loads(latest_trend.trend_json)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**🔥 Dominant Themes**")
                    for t in td.get("dominant_themes", [])[:5]:
                        st.markdown(f"- {t}")
                    st.markdown("**🌱 Emerging Topics**")
                    for t in td.get("emerging_topics", [])[:5]:
                        st.markdown(f"- {t}")
                with col_b:
                    st.markdown("**📉 Saturated Areas**")
                    for t in td.get("saturated_areas", [])[:3]:
                        st.markdown(f"- {t}")
                    st.markdown("**🔭 Underexplored Gaps**")
                    for t in td.get("underexplored_gaps", [])[:3]:
                        st.markdown(f"- {t}")

                summary = td.get("summary") or td.get("where_research_is_going", "")
                if summary:
                    st.info(summary)
            except Exception as e:
                st.warning(f"Could not parse trend data: {e}")
        else:
            st.info("Run **Analyze Trends** from the sidebar to see research directions.")

# ============================================================
# TAB 2: Daily Papers
# ============================================================
with tabs[1]:
    st.header("📄 Daily Papers")

    papers = load_papers(limit=500)

    if not papers:
        st.info("No papers yet. Click **Fetch Papers Now** in the sidebar.")
    else:
        # Filters
        st.subheader("🔎 Filters")
        col1, col2, col3 = st.columns(3)
        col4, col5, col6 = st.columns(3)

        all_cats = sorted(set(p.get("primary_category", "") for p in papers if p.get("primary_category")))
        all_areas = sorted(set(p.get("research_area", "") for p in papers if p.get("research_area")))
        all_dates = sorted(set(p.get("published_date", "")[:10] for p in papers if p.get("published_date")), reverse=True)

        with col1:
            cat_filter = st.selectbox("Category", ["All"] + all_cats)
        with col2:
            area_filter = st.selectbox("Research Area", ["All"] + all_areas)
        with col3:
            date_filter = st.selectbox("Date", ["All"] + all_dates[:30])
        with col4:
            keyword_filter = st.text_input("Keyword search", placeholder="e.g. transformer, RAG, agent...")
        with col5:
            min_novelty = st.slider("Min Novelty Score", 1, 10, 1)
        with col6:
            min_impact = st.slider("Min Impact Score", 1, 10, 1)

        # Apply filters
        filtered = papers
        if cat_filter != "All":
            filtered = [p for p in filtered if p.get("primary_category") == cat_filter]
        if area_filter != "All":
            filtered = [p for p in filtered if p.get("research_area") == area_filter]
        if date_filter != "All":
            filtered = [p for p in filtered if p.get("published_date", "").startswith(date_filter)]
        if keyword_filter:
            kw_lower = keyword_filter.lower()
            filtered = [
                p for p in filtered
                if kw_lower in p.get("title", "").lower()
                or kw_lower in p.get("abstract", "").lower()
                or kw_lower in p.get("one_line_summary", "").lower()
                or any(kw_lower in kw.lower() for kw in p.get("keywords", []))
            ]
        filtered = [p for p in filtered if p.get("novelty_score", 5) >= min_novelty]
        filtered = [p for p in filtered if p.get("impact_score", 5) >= min_impact]

        st.markdown(f"**Showing {len(filtered)} papers**")
        st.markdown("---")

        # Paper cards
        for p in filtered[:100]:
            with st.expander(f"📄 {p.get('title', 'Untitled')}", expanded=False):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    authors = p.get("authors", [])
                    if isinstance(authors, list):
                        authors_str = ", ".join(authors[:5])
                        if len(authors) > 5:
                            authors_str += f" +{len(authors)-5} more"
                    else:
                        authors_str = str(authors)
                    st.markdown(f"**Authors:** {authors_str}")
                    st.markdown(f"**arXiv ID:** `{p.get('arxiv_id', '')}` | **Category:** `{p.get('primary_category', '')}` | **Date:** {p.get('published_date', '')}")

                    summary = p.get("one_line_summary", "")
                    if summary:
                        st.markdown(f"**Summary:** {summary}")
                    else:
                        st.markdown(f"**Abstract:** {p.get('abstract', '')[:300]}...")

                    tags = p.get("trend_tags", [])
                    if tags:
                        st.markdown("**Tags:** " + " ".join([f"`{t}`" for t in tags[:8]]))

                with col_b:
                    novelty = p.get("novelty_score", "–")
                    impact = p.get("impact_score", "–")
                    st.metric("Novelty", f"{novelty}/10")
                    st.metric("Impact", f"{impact}/10")
                    arxiv_url = p.get("arxiv_url", f"https://arxiv.org/abs/{p.get('arxiv_id', '')}")
                    pdf_url = p.get("pdf_url", "")
                    st.markdown(f"[📖 arXiv]({arxiv_url}) | [📥 PDF]({pdf_url})")

        # Export
        st.markdown("---")
        if st.button("📥 Export filtered papers as CSV"):
            from app.services.export import papers_to_csv, make_export_filename
            csv_str = papers_to_csv(filtered)
            st.download_button(
                "Download CSV",
                data=csv_str,
                file_name=make_export_filename("papers", "csv"),
                mime="text/csv",
            )

# ============================================================
# TAB 3: Deep Analysis
# ============================================================
with tabs[2]:
    st.header("🔍 Paper Deep Analysis")

    papers = load_papers(limit=500)

    if not papers:
        st.info("No papers yet.")
    else:
        titles = [f"{p.get('title', 'Untitled')[:80]} ({p.get('arxiv_id', '')})" for p in papers]
        selected_idx = st.selectbox("Select a paper", range(len(titles)), format_func=lambda i: titles[i])
        paper = papers[selected_idx]

        st.markdown("---")

        # Paper header
        st.subheader(paper.get("title", ""))
        authors = paper.get("authors", [])
        if isinstance(authors, list):
            st.markdown(f"**Authors:** {', '.join(authors[:8])}")
        col_a, col_b, col_c = st.columns(3)
        col_a.markdown(f"**Category:** `{paper.get('primary_category', '')}`")
        col_b.markdown(f"**Published:** {paper.get('published_date', '')}")
        col_c.markdown(f"[📖 arXiv]({paper.get('arxiv_url', '')}) | [📥 PDF]({paper.get('pdf_url', '')})")

        st.markdown("---")

        # Two-column layout
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**📋 Abstract**")
            st.markdown(paper.get("abstract", "No abstract available."))

            if paper.get("one_line_summary"):
                st.markdown("**🎯 One-Line Summary**")
                st.info(paper.get("one_line_summary"))

            if paper.get("problem"):
                st.markdown("**❓ Problem Statement**")
                st.markdown(paper.get("problem"))

            if paper.get("method"):
                st.markdown("**⚙️ Method**")
                st.markdown(paper.get("method"))

        with col_right:
            if paper.get("main_contribution"):
                st.markdown("**🏆 Main Contribution**")
                st.markdown(paper.get("main_contribution"))

            datasets = paper.get("datasets_or_benchmarks", [])
            if datasets:
                st.markdown("**📊 Datasets / Benchmarks**")
                if isinstance(datasets, list):
                    for d in datasets:
                        st.markdown(f"- {d}")
                else:
                    st.markdown(str(datasets))

            if paper.get("results_or_claims"):
                st.markdown("**📈 Results / Claims**")
                st.markdown(paper.get("results_or_claims"))

            if paper.get("limitations"):
                st.markdown("**⚠️ Limitations**")
                st.markdown(paper.get("limitations"))

            if paper.get("future_work"):
                st.markdown("**🔮 Future Work**")
                st.markdown(paper.get("future_work"))

        # Scores
        st.markdown("---")
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
        sc1.metric("Novelty", f"{paper.get('novelty_score', '–')}/10")
        sc2.metric("Impact", f"{paper.get('impact_score', '–')}/10")
        sc3.metric("Depth", f"{paper.get('technical_depth_score', '–')}/10")
        sc4.metric("Difficulty", f"{paper.get('implementation_difficulty_score', '–')}/10")
        sc5.metric("Reproducibility", f"{paper.get('reproducibility_score', '–')}/10")
        sc6.metric("Code Potential", f"{paper.get('code_generation_potential', '–')}/10")

        st.markdown("---")

        # Action buttons
        if not is_api_key_configured():
            st.warning("Add OPENROUTER_API_KEY to enable AI analysis features.")
        else:
            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)

            with col_b1:
                if st.button("🔄 Re-analyze"):
                    with st.spinner("Re-analyzing..."):
                        from app.agents.paper_summarizer_agent import PaperSummarizerAgent
                        agent = PaperSummarizerAgent(skip_existing=False)
                        agent.summarize_paper(paper.get("id"), paper.get("title"), paper.get("abstract"))
                        st.success("Done!")
                        st.cache_data.clear()
                        st.rerun()

            with col_b2:
                if st.button("📄 Extract PDF"):
                    with st.spinner("Downloading and extracting PDF..."):
                        from app.agents.pdf_reader_agent import PDFReaderAgent
                        agent = PDFReaderAgent()
                        text = agent.run(paper.get("pdf_url", ""))
                        if text:
                            st.session_state[f"pdf_text_{paper.get('arxiv_id')}"] = text[:5000]
                            st.success(f"Extracted {len(text):,} characters")
                        else:
                            st.error("PDF extraction failed.")

            if f"pdf_text_{paper.get('arxiv_id')}" in st.session_state:
                with st.expander("📄 PDF Text Preview"):
                    st.text(st.session_state[f"pdf_text_{paper.get('arxiv_id')}"])

            with col_b3:
                if st.button("🔬 Deep Explanation"):
                    with st.spinner("Generating deep explanation..."):
                        from app.agents.code_generator_agent import CodeGeneratorAgent
                        agent = CodeGeneratorAgent()
                        result = agent.generate_technical_explanation(paper)
                        st.session_state["deep_explanation"] = result

            with col_b4:
                if st.button("📚 Literature Review"):
                    with st.spinner("Generating literature review paragraph..."):
                        from app.agents.research_gap_agent import ResearchGapAgent
                        agent = ResearchGapAgent()
                        result = agent.generate_literature_review(paper)
                        st.session_state["lit_review"] = result

            with col_b5:
                if st.button("💡 Research Ideas"):
                    with st.spinner("Generating research ideas..."):
                        from app.agents.research_gap_agent import ResearchGapAgent
                        agent = ResearchGapAgent()
                        result = agent.generate_research_ideas(paper)
                        st.session_state["research_ideas"] = result

            # Show results
            for key, label in [
                ("deep_explanation", "🔬 Deep Technical Explanation"),
                ("lit_review", "📚 Literature Review Paragraph"),
                ("research_ideas", "💡 Research Ideas"),
            ]:
                if key in st.session_state and st.session_state[key]:
                    st.markdown(f"### {label}")
                    st.markdown(st.session_state[key])
                    st.download_button(
                        f"Download {label}",
                        data=st.session_state[key],
                        file_name=f"{key}_{paper.get('arxiv_id', 'paper')}.md",
                        mime="text/markdown",
                    )

# ============================================================
# TAB 4: Trend Analytics
# ============================================================
with tabs[3]:
    st.header("📈 Trend Analytics")

    papers = load_papers(limit=500)

    if not papers:
        st.info("Fetch and summarize papers to see trends.")
    else:
        from app.agents.trend_analyst_agent import TrendAnalystAgent
        from app.agents.benchmark_extractor_agent import BenchmarkExtractorAgent
        from app.services.clustering import cluster_papers, get_cluster_summary

        analyst = TrendAnalystAgent()
        cat_stats = analyst.get_category_stats(papers)
        kw_freq = analyst.get_keyword_freq(papers)
        tag_freq = analyst.get_trend_tag_freq(papers)

        # --- Category trend ---
        col1, col2 = st.columns(2)
        with col1:
            if cat_stats:
                df = pd.DataFrame(list(cat_stats.items()), columns=["Category", "Count"])
                fig = px.pie(df, values="Count", names="Category", title="Research Category Distribution")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if kw_freq:
                df_kw = pd.DataFrame(list(kw_freq.items())[:25], columns=["Keyword", "Count"])
                fig = px.treemap(df_kw, path=["Keyword"], values="Count", title="Keyword Frequency Treemap")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

        # --- Trend tags bar ---
        if tag_freq:
            df_tags = pd.DataFrame(list(tag_freq.items()), columns=["Tag", "Count"])
            fig = px.bar(df_tags, x="Tag", y="Count", title="Research Trend Tags",
                         color="Count", color_continuous_scale="Viridis")
            fig.update_layout(height=350, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        # --- Research areas ---
        area_counts = Counter(p.get("research_area", "") for p in papers if p.get("research_area"))
        if area_counts:
            df_area = pd.DataFrame(area_counts.most_common(15), columns=["Area", "Count"])
            fig = px.bar(df_area, x="Count", y="Area", orientation="h",
                         title="Research Areas", color="Count",
                         color_continuous_scale="Purples")
            fig.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)

        # --- Paper clustering ---
        st.markdown("---")
        st.subheader("🗂️ Paper Clusters")

        n_clusters = st.slider("Number of clusters", 2, 12, 6)
        if st.button("🔄 Compute Clusters"):
            with st.spinner("Clustering papers..."):
                clustered, labels = cluster_papers(papers, n_clusters=n_clusters)
                cluster_summary = get_cluster_summary(clustered)
                st.session_state["cluster_summary"] = cluster_summary
                st.session_state["clustered_papers"] = clustered

        if "cluster_summary" in st.session_state:
            cs = st.session_state["cluster_summary"]
            for label, paper_titles in cs.items():
                with st.expander(f"📦 {label} ({len(paper_titles)} papers)"):
                    for t in paper_titles[:10]:
                        st.markdown(f"- {t}")

        # --- Benchmark analysis ---
        st.markdown("---")
        st.subheader("📊 Benchmark & Dataset Trends")

        if st.button("🔄 Extract Benchmarks"):
            with st.spinner("Extracting benchmarks..."):
                bench_agent = BenchmarkExtractorAgent()
                bench_data = bench_agent.run()
                st.session_state["bench_data"] = bench_data

        if "bench_data" in st.session_state:
            bd = st.session_state["bench_data"]
            col_a, col_b = st.columns(2)
            with col_a:
                ds_freq = bd.get("dataset_frequency", {})
                if ds_freq:
                    df_ds = pd.DataFrame(list(ds_freq.items())[:20], columns=["Dataset", "Count"])
                    fig = px.bar(df_ds, x="Dataset", y="Count", title="Dataset Usage Frequency",
                                 color="Count", color_continuous_scale="Teal")
                    fig.update_layout(height=350, xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
            with col_b:
                mt_freq = bd.get("metric_frequency", {})
                if mt_freq:
                    df_mt = pd.DataFrame(list(mt_freq.items())[:20], columns=["Metric", "Count"])
                    fig = px.bar(df_mt, x="Metric", y="Count", title="Evaluation Metric Frequency",
                                 color="Count", color_continuous_scale="Magma")
                    fig.update_layout(height=350, xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)

        # --- LLM trend summary ---
        st.markdown("---")
        st.subheader("🧠 LLM Trend Summary")

        session = get_session()
        try:
            from app.database import DailyTrend
            latest = session.query(DailyTrend).order_by(DailyTrend.created_at.desc()).first()
        finally:
            session.close()

        if latest:
            td = json.loads(latest.trend_json)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown("**🔥 Dominant Themes**")
                for t in td.get("dominant_themes", [])[:6]:
                    st.markdown(f"- {t}")
            with col_b:
                st.markdown("**🌱 Emerging Topics**")
                for t in td.get("emerging_topics", [])[:6]:
                    st.markdown(f"- {t}")
                st.markdown("**🏃 Fastest Growing**")
                for t in td.get("fastest_growing", [])[:4]:
                    st.markdown(f"- {t}")
            with col_c:
                st.markdown("**📉 Saturated Areas**")
                for t in td.get("saturated_areas", [])[:4]:
                    st.markdown(f"- {t}")
                st.markdown("**🔭 Gaps**")
                for t in td.get("underexplored_gaps", [])[:4]:
                    st.markdown(f"- {t}")

            if td.get("summary"):
                st.markdown("**Summary**")
                st.info(td["summary"])
        else:
            st.info("Click **Analyze Trends** in the sidebar to generate trend analysis.")

# ============================================================
# TAB 5: Agentic Tools
# ============================================================
with tabs[4]:
    st.header("🤖 Agentic Research Tools")

    st.markdown("""
    This tab exposes all research agents directly. Each agent can be run independently
    or in sequence for a full research pipeline.
    """)

    if not is_api_key_configured():
        st.error("⚠️ Set OPENROUTER_API_KEY in your .env file to use AI agents.")

    st.markdown("---")

    # Agent 1: Paper Collector
    with st.expander("📥 1. PaperCollectorAgent — Fetch papers from arXiv", expanded=False):
        st.markdown("Fetches papers from configured arXiv categories and saves to the database.")
        cats_default = os.getenv("FETCH_CATEGORIES", "cs.CL,cs.AI,cs.LG,cs.CV,cs.RO")
        col1, col2 = st.columns(2)
        with col1:
            cats_input = st.text_input("Categories (comma-separated)", value=cats_default)
        with col2:
            max_res = st.number_input("Max results", min_value=1, max_value=200, value=50)
        if st.button("▶ Run PaperCollectorAgent"):
            with st.spinner("Fetching..."):
                from app.agents.paper_collector_agent import PaperCollectorAgent
                agent = PaperCollectorAgent(
                    categories=[c.strip() for c in cats_input.split(",")],
                    max_results=int(max_res)
                )
                papers_collected = agent.run()
                st.success(f"Collected {len(papers_collected)} papers!")
                st.cache_data.clear()

    # Agent 2: Paper Summarizer
    with st.expander("🤖 2. PaperSummarizerAgent — Summarize using OpenRouter", expanded=False):
        st.markdown("Uses GPT-4o mini to generate structured summaries for all unsummarized papers.")
        skip = st.checkbox("Skip already summarized papers", value=True)
        if st.button("▶ Run PaperSummarizerAgent", disabled=not is_api_key_configured()):
            papers = load_papers(limit=500)
            unsummarized = [p for p in papers if not p.get("one_line_summary")] if skip else papers
            if not unsummarized:
                st.info("All papers are already summarized!")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(done, total):
                    progress_bar.progress(done / total)
                    status_text.text(f"Summarized {done}/{total}")

                from app.agents.paper_summarizer_agent import PaperSummarizerAgent
                agent = PaperSummarizerAgent(skip_existing=skip)
                results = agent.run(progress_callback=update_progress)
                st.success(f"Summarized {len(results)} papers!")
                st.cache_data.clear()

    # Agent 3: PDF Reader
    with st.expander("📄 3. PDFReaderAgent — Extract full paper text", expanded=False):
        st.markdown("Downloads and extracts text from an arXiv PDF.")
        pdf_url_input = st.text_input("PDF URL", placeholder="https://arxiv.org/pdf/2401.12345")
        if st.button("▶ Run PDFReaderAgent"):
            if pdf_url_input:
                with st.spinner("Downloading and extracting..."):
                    from app.agents.pdf_reader_agent import PDFReaderAgent
                    agent = PDFReaderAgent()
                    text = agent.run(pdf_url_input)
                    if text:
                        st.success(f"Extracted {len(text):,} characters")
                        st.text_area("Extracted Text (first 3000 chars)", text[:3000], height=300)
                    else:
                        st.error("Extraction failed.")
            else:
                st.warning("Enter a PDF URL.")

    # Agent 4: Trend Analyst
    with st.expander("📊 4. TrendAnalystAgent — Identify research trends", expanded=False):
        st.markdown("Analyzes all stored summaries to identify dominant themes, emerging topics, and gaps.")
        if st.button("▶ Run TrendAnalystAgent", disabled=not is_api_key_configured()):
            with st.spinner("Analyzing trends..."):
                from app.agents.trend_analyst_agent import TrendAnalystAgent
                agent = TrendAnalystAgent()
                result = agent.run(save=True)
                if result:
                    st.json(result)
                else:
                    st.error("Analysis failed or no papers available.")

    # Agent 5: Research Gap
    with st.expander("🔭 5. ResearchGapAgent — Find underexplored directions", expanded=False):
        st.markdown("Identifies underexplored research areas and suggests publishable project ideas.")
        if st.button("▶ Run ResearchGapAgent", disabled=not is_api_key_configured()):
            with st.spinner("Finding gaps..."):
                from app.agents.research_gap_agent import ResearchGapAgent
                agent = ResearchGapAgent()
                result = agent.run()
                if result:
                    st.subheader("Underexplored Areas")
                    for item in result.get("underexplored_areas", []):
                        with st.expander(item.get("area", "Area")):
                            st.markdown(f"**Reason:** {item.get('reason', '')}")
                            st.markdown(f"**Opportunity:** {item.get('opportunity', '')}")
                            st.markdown(f"**Difficulty:** {item.get('difficulty', '')} | **Novelty:** {item.get('novelty', '')}")
                    st.subheader("Publishable Project Directions")
                    for proj in result.get("publishable_directions", []):
                        with st.expander(proj.get("title", "Project")):
                            st.markdown(f"**Idea:** {proj.get('idea', '')}")
                            st.markdown(f"**Gap addressed:** {proj.get('gap_addressed', '')}")
                            st.markdown(f"**Approach:** {proj.get('approach', '')}")
                else:
                    st.error("No results.")

    # Agent 6: Code Generator
    with st.expander("💻 6. CodeGeneratorAgent — Generate code from paper", expanded=False):
        st.markdown("Go to the **Generate Code** tab for the full code generation interface.")

    # Agent 7: Report Writer
    with st.expander("📝 7. ReportWriterAgent — Generate research reports", expanded=False):
        st.markdown("Go to the **Research Reports** tab for the full report interface.")

    # Agent 8: Benchmark Extractor
    with st.expander("📊 8. BenchmarkExtractorAgent — Extract datasets & benchmarks", expanded=False):
        st.markdown("Extracts and aggregates dataset, metric, and baseline usage across all papers.")
        if st.button("▶ Run BenchmarkExtractorAgent"):
            with st.spinner("Extracting..."):
                from app.agents.benchmark_extractor_agent import BenchmarkExtractorAgent
                agent = BenchmarkExtractorAgent()
                result = agent.run()
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Top Datasets**")
                    for ds, cnt in list(result.get("dataset_frequency", {}).items())[:10]:
                        st.markdown(f"- {ds}: {cnt}")
                with col2:
                    st.markdown("**Top Metrics**")
                    for mt, cnt in list(result.get("metric_frequency", {}).items())[:10]:
                        st.markdown(f"- {mt}: {cnt}")

    # Agent 9: Paper Ranker
    with st.expander("🏆 9. PaperRankerAgent — Rank papers by scores", expanded=False):
        st.markdown("Ranks papers using weighted composite scores (novelty, impact, depth, etc.)")
        sort_options = ["composite", "novelty", "impact", "technical_depth", "implementation", "reproducibility"]
        sort_by = st.selectbox("Sort by", sort_options)
        top_n = st.slider("Top N papers", 5, 50, 10)
        if st.button("▶ Run PaperRankerAgent"):
            from app.agents.paper_ranker_agent import PaperRankerAgent
            agent = PaperRankerAgent()
            ranked = agent.top_n(n=top_n, sort_by=sort_by)
            for paper in ranked:
                st.markdown(
                    f"**#{paper['rank']}** [{paper.get('title', '')[:70]}]({paper.get('arxiv_url', '')}) "
                    f"— Composite: **{paper.get('composite_score', '–')}** | "
                    f"Novelty: {paper.get('novelty_score', '–')} | Impact: {paper.get('impact_score', '–')}"
                )

# ============================================================
# TAB 6: Generate Code
# ============================================================
with tabs[5]:
    st.header("💻 Generate Code from Paper")

    if not is_api_key_configured():
        st.warning("⚠️ Set OPENROUTER_API_KEY in .env to use code generation.")

    papers = load_papers(limit=500)
    if not papers:
        st.info("No papers yet. Fetch some first.")
    else:
        from app.agents.code_generator_agent import CodeGeneratorAgent, CODE_MODES

        titles = [f"{p.get('title', '')[:80]} ({p.get('arxiv_id', '')})" for p in papers]
        selected_idx = st.selectbox("Select paper", range(len(titles)), format_func=lambda i: titles[i], key="code_paper_select")
        paper = papers[selected_idx]

        st.markdown(f"**{paper.get('title', '')}**")
        st.markdown(f"arXiv: [{paper.get('arxiv_id', '')}]({paper.get('arxiv_url', '')})")

        col_mode, col_cache = st.columns([3, 1])
        with col_mode:
            code_mode = st.selectbox("Code generation mode", CODE_MODES)
        with col_cache:
            use_cache = st.checkbox("Use cached result", value=True)

        # Optional: PDF text
        full_text = ""
        if st.checkbox("Include PDF text (slower but better)"):
            if st.button("Download PDF first"):
                with st.spinner("Downloading PDF..."):
                    from app.agents.pdf_reader_agent import PDFReaderAgent
                    pdf_agent = PDFReaderAgent()
                    full_text = pdf_agent.run(paper.get("pdf_url", ""))
                    if full_text:
                        st.session_state["code_pdf_text"] = full_text
                        st.success(f"Extracted {len(full_text):,} characters")
            full_text = st.session_state.get("code_pdf_text", "")

        if st.button("🚀 Generate Code", disabled=not is_api_key_configured(), type="primary"):
            with st.spinner(f"Generating: {code_mode}..."):
                agent = CodeGeneratorAgent()
                result = agent.run(paper, code_mode, full_text=full_text, use_cache=use_cache)
                st.session_state["generated_code_result"] = result
                st.session_state["generated_code_paper"] = paper
                st.session_state["generated_code_mode"] = code_mode

        if "generated_code_result" in st.session_state:
            result = st.session_state["generated_code_result"]
            paper_for_dl = st.session_state.get("generated_code_paper", paper)
            mode_for_dl = st.session_state.get("generated_code_mode", code_mode)

            st.markdown("---")
            st.markdown(result)

            col_dl1, col_dl2, col_dl3 = st.columns(3)
            arxiv_id = paper_for_dl.get("arxiv_id", "paper")

            with col_dl1:
                from app.services.export import code_to_py
                py_code = code_to_py(result, paper_for_dl.get("title", ""))
                st.download_button(
                    "⬇️ Download as .py",
                    data=py_code,
                    file_name=f"{arxiv_id}_implementation.py",
                    mime="text/plain",
                )

            with col_dl2:
                st.download_button(
                    "⬇️ Download as .md",
                    data=result,
                    file_name=f"{arxiv_id}_{mode_for_dl.replace(' ', '_')}.md",
                    mime="text/markdown",
                )

            with col_dl3:
                readme_prefix = f"# Reproduction: {paper_for_dl.get('title', '')}\n\narXiv: {paper_for_dl.get('arxiv_url', '')}\n\n---\n\n"
                st.download_button(
                    "⬇️ Download README",
                    data=readme_prefix + result,
                    file_name=f"{arxiv_id}_README.md",
                    mime="text/markdown",
                )

# ============================================================
# TAB 7: Research Reports
# ============================================================
with tabs[6]:
    st.header("📝 Research Report Generator")

    if not is_api_key_configured():
        st.warning("⚠️ Set OPENROUTER_API_KEY in .env to generate reports.")

    from app.agents.report_writer_agent import ReportWriterAgent, REPORT_TYPES

    col1, col2 = st.columns(2)
    with col1:
        report_type = st.selectbox("Report type", REPORT_TYPES)
    with col2:
        cat_for_report = st.text_input("Category filter (optional)", placeholder="cs.LG, cs.CL, etc.")

    if st.button("📝 Generate Report", disabled=not is_api_key_configured(), type="primary"):
        with st.spinner(f"Generating {report_type}..."):
            agent = ReportWriterAgent()
            report_content = agent.run(
                report_type=report_type,
                category=cat_for_report.strip() or None,
                save=True,
            )
            st.session_state["report_content"] = report_content
            st.session_state["report_type"] = report_type

    if "report_content" in st.session_state:
        content = st.session_state["report_content"]
        rtype = st.session_state.get("report_type", "report")

        st.markdown("---")
        st.markdown(content)
        st.markdown("---")

        # Download buttons
        col1, col2, col3, col4 = st.columns(4)
        today = date.today().isoformat()

        with col1:
            st.download_button("⬇️ Markdown", data=content,
                               file_name=f"report_{today}.md", mime="text/markdown")
        with col2:
            from app.services.export import report_to_txt
            st.download_button("⬇️ TXT", data=report_to_txt(content),
                               file_name=f"report_{today}.txt", mime="text/plain")
        with col3:
            report_json = json.dumps({"type": rtype, "date": today, "content": content}, indent=2)
            st.download_button("⬇️ JSON", data=report_json,
                               file_name=f"report_{today}.json", mime="application/json")
        with col4:
            papers_for_csv = load_papers(limit=100)
            from app.services.export import papers_to_csv
            st.download_button("⬇️ CSV Summary", data=papers_to_csv(papers_for_csv),
                               file_name=f"papers_{today}.csv", mime="text/csv")

    # --- Past reports ---
    st.markdown("---")
    st.subheader("📚 Past Reports")
    session = get_session()
    try:
        from app.database import Report as ReportModel
        past_reports = session.query(ReportModel).order_by(ReportModel.created_at.desc()).limit(20).all()
    finally:
        session.close()

    if past_reports:
        for r in past_reports:
            with st.expander(f"[{r.report_type}] {r.title} — {str(r.created_at)[:10]}"):
                st.markdown(r.content_markdown[:500] + "...")
                st.download_button(
                    "Download full report",
                    data=r.content_markdown,
                    file_name=f"report_{r.id}.md",
                    mime="text/markdown",
                    key=f"dl_report_{r.id}",
                )
    else:
        st.info("No past reports. Generate one above.")

# ============================================================
# TAB 8: Knowledge Graph
# ============================================================
with tabs[7]:
    st.header("🧠 Knowledge Graph")
    st.markdown(
        "Explore the persistent research memory built from all analysed papers. "
        "Entities, relationships, trend metrics, and research gaps grow with every ingestion."
    )

    from app.database import (
        KGEntity, KGEdge, PaperEntityMention, TrendMemory,
        get_kg_stats, AgentMemory,
    )
    from app.memory.research_memory_engine import ResearchMemoryEngine as _RME

    _rme = _RME()

    @st.cache_data(ttl=60)
    def _kg_stats():
        s = get_session()
        try:
            return get_kg_stats(s)
        finally:
            s.close()

    @st.cache_data(ttl=60)
    def _top_entities(etype=None, n=30):
        s = get_session()
        try:
            q = s.query(KGEntity)
            if etype:
                q = q.filter_by(entity_type=etype)
            rows = q.order_by(KGEntity.frequency_count.desc()).limit(n).all()
            return [{"id": r.id, "type": r.entity_type, "name": r.name,
                     "freq": r.frequency_count, "first_seen": r.first_seen_date,
                     "last_seen": r.last_seen_date, "confidence": r.confidence_score} for r in rows]
        finally:
            s.close()

    @st.cache_data(ttl=60)
    def _trending_entities(window=7, n=20):
        return _rme.get_trending_entities(window_days=window, limit=n)

    @st.cache_data(ttl=60)
    def _research_gaps(n=20):
        return _rme.find_research_gaps(limit=n)

    kg_stats = _kg_stats()

    # --- KG Metrics row ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🔵 Entities", kg_stats.get("entities", 0))
    c2.metric("🔗 Relationships", kg_stats.get("edges", 0))
    c3.metric("📌 Mentions", kg_stats.get("mentions", 0))
    c4.metric("🧩 Semantic Memories", kg_stats.get("semantic_memories", 0))
    c5.metric("📈 Trend Records", kg_stats.get("trend_records", 0))

    st.markdown("---")

    # --- Build KG button ---
    col_build, col_gap = st.columns(2)
    with col_build:
        if st.button("🔨 Build / Update Knowledge Graph", use_container_width=True,
                     disabled=not is_api_key_configured()):
            with st.spinner("Running KnowledgeGraphBuilderAgent on unprocessed papers…"):
                from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
                agent = KnowledgeGraphBuilderAgent()
                results = agent.run(limit=20)
                st.cache_data.clear()
                st.success(f"Processed {len(results)} papers into KG!")
                st.rerun()
    with col_gap:
        if st.button("🕳️ Scan Research Gaps", use_container_width=True):
            with st.spinner("Scanning for research gaps…"):
                from app.agents.research_gap_memory_agent import ResearchGapMemoryAgent
                agent = ResearchGapMemoryAgent()
                gaps = agent.run(limit=30)
                st.cache_data.clear()
                st.success(f"Promoted {len(gaps)} research gaps!")
                st.rerun()

    st.markdown("---")

    # --- Entity Explorer ---
    kg_subtab1, kg_subtab2, kg_subtab3, kg_subtab4 = st.tabs(
        ["🔵 Entities", "🔗 Relationships", "📈 Trends", "🕳️ Research Gaps"]
    )

    with kg_subtab1:
        st.subheader("Top Entities by Frequency")
        etype_filter = st.selectbox(
            "Filter by entity type",
            ["All"] + [
                "Author", "Method", "Dataset", "Task", "Benchmark", "Metric",
                "Baseline", "Limitation", "FutureWork", "ResearchArea", "Topic",
                "ModelArchitecture", "Tool", "Library", "ResearchGap", "CodeRepository",
            ],
            key="kg_etype_filter",
        )
        selected_type = None if etype_filter == "All" else etype_filter
        entities_data = _top_entities(etype=selected_type, n=50)

        if entities_data:
            df_ent = pd.DataFrame(entities_data)
            # Bar chart of top 20
            fig_ent = px.bar(
                df_ent.head(20), x="freq", y="name", orientation="h",
                color="freq", color_continuous_scale="Blues",
                title=f"Top {min(20, len(df_ent))} Entities — {etype_filter}",
            )
            fig_ent.update_layout(height=500, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_ent, use_container_width=True)

            # Full table
            st.dataframe(
                df_ent[["type", "name", "freq", "confidence", "first_seen", "last_seen"]],
                use_container_width=True,
            )

            # Entity type distribution pie
            if etype_filter == "All":
                all_entities = _top_entities(n=500)
                type_counts = Counter(e["type"] for e in all_entities)
                df_pie = pd.DataFrame(type_counts.items(), columns=["Entity Type", "Count"])
                fig_pie = px.pie(df_pie, names="Entity Type", values="Count",
                                 title="Entity Type Distribution")
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No entities in the knowledge graph yet. Run **Build / Update Knowledge Graph** above.")

        # --- Graph Neighbourhood Explorer ---
        st.markdown("---")
        st.subheader("🔭 Explore Entity Neighbourhood")
        search_ent = st.text_input("Entity name to explore (e.g. 'RAG', 'LoRA', 'RLHF')", key="kg_nbr_search")
        nbr_depth = st.slider("Hop depth", 1, 3, 2, key="kg_nbr_depth")
        if search_ent:
            neighbours = _rme.get_related_entities(search_ent, depth=nbr_depth, limit=50)
            if neighbours:
                df_nbr = pd.DataFrame(neighbours)
                st.markdown(f"**{len(neighbours)} related entities found for '{search_ent}'**")
                st.dataframe(df_nbr[["type", "name", "relationship", "frequency", "confidence"]], use_container_width=True)
                # Simple network as a bar chart (relationships count)
                rel_counts = Counter(n["relationship"] for n in neighbours)
                fig_rel = px.bar(
                    x=list(rel_counts.keys()), y=list(rel_counts.values()),
                    labels={"x": "Relationship", "y": "Count"},
                    title=f"Relationship types to/from '{search_ent}'",
                    color=list(rel_counts.values()), color_continuous_scale="Purples",
                )
                st.plotly_chart(fig_rel, use_container_width=True)
            else:
                st.warning(f"No entity found matching '{search_ent}'.")

    with kg_subtab2:
        st.subheader("Top Relationship Types")
        s = get_session()
        try:
            from sqlalchemy import func as _sqlfunc
            rel_counts_raw = (
                s.query(KGEdge.relationship_type, _sqlfunc.count(KGEdge.id))
                .group_by(KGEdge.relationship_type)
                .order_by(_sqlfunc.count(KGEdge.id).desc())
                .all()
            )
        finally:
            s.close()

        if rel_counts_raw:
            df_rels = pd.DataFrame(rel_counts_raw, columns=["Relationship", "Count"])
            fig_rels = px.bar(df_rels, x="Count", y="Relationship", orientation="h",
                              color="Count", color_continuous_scale="Greens",
                              title="Relationship Type Frequency")
            fig_rels.update_layout(height=450, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_rels, use_container_width=True)
            st.dataframe(df_rels, use_container_width=True)
        else:
            st.info("No relationships yet. Run the KG builder to extract them.")

        # Paper–Entity Similarity
        st.markdown("---")
        st.subheader("🔁 Find Similar Papers via Entity Overlap")
        all_papers_kg = load_papers(limit=200)
        if all_papers_kg:
            paper_options = {p["title"][:80]: p["id"] for p in all_papers_kg if p.get("title")}
            sel_title = st.selectbox("Select a paper", list(paper_options.keys()), key="kg_sim_paper")
            if sel_title:
                sel_pid = paper_options[sel_title]
                similar = _rme.find_similar_papers(sel_pid, limit=10)
                if similar:
                    df_sim = pd.DataFrame(similar)
                    st.dataframe(df_sim[["arxiv_id", "title", "similarity_score", "shared_entities"]],
                                 use_container_width=True)
                else:
                    st.info("No similar papers found via entity overlap. Ingest more papers into the KG first.")

    with kg_subtab3:
        st.subheader("📈 Trending Entities")
        trend_window = st.select_slider("Time window (days)", [3, 7, 14, 30], value=7, key="kg_trend_window")
        trend_type = st.selectbox("Entity type", ["All", "Method", "Dataset", "Topic", "Task", "Benchmark"], key="kg_trend_type")
        trending = _trending_entities(window=trend_window, n=20)
        if trend_type != "All":
            trending = [t for t in trending if t.get("type") == trend_type]

        if trending:
            df_trend = pd.DataFrame(trending)
            col_tr1, col_tr2 = st.columns(2)
            with col_tr1:
                fig_vel = px.bar(df_trend.head(15), x="velocity", y="name", orientation="h",
                                 color="velocity", color_continuous_scale="Reds",
                                 title="Topic Velocity (acceleration)")
                fig_vel.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_vel, use_container_width=True)
            with col_tr2:
                fig_sat = px.bar(df_trend.head(15), x="saturation", y="name", orientation="h",
                                 color="saturation", color_continuous_scale="Oranges",
                                 title="Topic Saturation")
                fig_sat.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig_sat, use_container_width=True)

            st.dataframe(df_trend[["type", "name", "velocity", "saturation", "novelty", "total_mentions"]],
                         use_container_width=True)
        else:
            st.info("No trend data yet. Ingest more papers with the KG builder to populate trends.")

        # Novel metric showcase
        st.markdown("---")
        st.subheader("🆕 Novel Graph Metrics for a Paper")
        all_papers_nm = load_papers(limit=200)
        if all_papers_nm:
            paper_options_nm = {p["title"][:80]: p["id"] for p in all_papers_nm if p.get("title")}
            sel_nm = st.selectbox("Select paper", list(paper_options_nm.keys()), key="kg_nm_paper")
            if sel_nm:
                sel_nm_pid = paper_options_nm[sel_nm]
                metrics = _rme.compute_novel_metrics(sel_nm_pid)
                if metrics:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🚀 Impl. Potential", f"{metrics.get('implementation_potential', 0):.0%}")
                    m2.metric("🌐 Cross-Domain", f"{metrics.get('cross_domain_score', 0):.0%}")
                    m3.metric("💡 Novel Combo", f"{metrics.get('novel_combination_score', 0):.0%}")
                    m4.metric("⚡ Topic Velocity", f"{metrics.get('topic_velocity', 0):.3f}")
                    mm1, mm2, mm3 = st.columns(3)
                    mm1.metric("🔥 Saturation", f"{metrics.get('topic_saturation', 0):.0%}")
                    mm2.metric("🗂️ Entity Count", metrics.get("entity_count", 0))
                    mm3.metric("💻 Has Code", "✅" if metrics.get("has_code") else "❌")
                else:
                    st.info("No KG entities for this paper yet. Run the KG builder first.")

    with kg_subtab4:
        st.subheader("🕳️ Research Gaps & Opportunities")
        st.markdown(
            "Repeated unresolved limitations and future-work items from across all papers, "
            "ranked by opportunity score."
        )
        area_filter = st.text_input("Filter by research area / keyword", key="kg_gap_area")
        gaps = _research_gaps(n=30)
        if area_filter:
            gaps = [g for g in gaps if area_filter.lower() in g["name"].lower()
                    or area_filter.lower() in g.get("description", "").lower()]

        if gaps:
            df_gaps = pd.DataFrame(gaps)
            color_col = "implementation_potential" if "implementation_potential" in df_gaps.columns else "gap_score"
            fig_gaps = px.scatter(
                df_gaps, x="frequency", y="gap_score",
                size="frequency", color=color_col,
                hover_name="name", color_continuous_scale="RdYlGn",
                title="Research Gaps — Frequency vs Opportunity Score",
                labels={"frequency": "Times Mentioned", "gap_score": "Opportunity Score",
                        "implementation_potential": "Impl. Potential"},
            )
            st.plotly_chart(fig_gaps, use_container_width=True)

            for g in gaps[:15]:
                with st.expander(f"🕳️ {g['name']} (score={g['gap_score']}, freq={g['frequency']})"):
                    c_g1, c_g2, c_g3 = st.columns(3)
                    c_g1.metric("Gap Score", g["gap_score"])
                    c_g2.metric("Frequency", g["frequency"])
                    c_g3.metric("Impl. Potential", f"{g.get('implementation_potential', 0):.0%}")
                    st.caption(f"Type: {g['type']} | First seen: {g['first_seen']} | Last seen: {g['last_seen']}")
        else:
            st.info("No research gaps found. Run **Scan Research Gaps** above after ingesting papers.")

    # --- Memory-Aware Reports ---
    st.markdown("---")
    st.subheader("📊 Memory Intelligence Reports")
    from app.agents.memory_aware_report_writer_agent import MEMORY_REPORT_TYPES, MemoryAwareReportWriterAgent
    sel_mem_report = st.selectbox("Report type", MEMORY_REPORT_TYPES, key="kg_mem_report_type")
    if st.button("📝 Generate Memory Intelligence Report", use_container_width=True,
                 disabled=not is_api_key_configured()):
        with st.spinner("Generating memory-aware report…"):
            agent = MemoryAwareReportWriterAgent()
            report = agent.run(report_type=sel_mem_report, save=True)
            st.session_state["mem_report"] = report

    if "mem_report" in st.session_state:
        st.markdown(st.session_state["mem_report"])
        st.download_button(
            "⬇️ Download Report",
            data=st.session_state["mem_report"],
            file_name=f"memory_report_{date.today().isoformat()}.md",
            mime="text/markdown",
        )


# ============================================================
# TAB 9: Memory Search
# ============================================================
with tabs[8]:
    st.header("🔮 Memory Search")
    st.markdown(
        "Query the persistent research memory with natural language. "
        "Answers draw from the knowledge graph, semantic memory chunks, trend records, and entity names."
    )

    from app.memory.research_memory_engine import ResearchMemoryEngine as _RME2
    _rme2 = _RME2()

    # --- Search bar ---
    st.markdown("### Ask the research memory…")
    memory_query = st.text_input(
        "Query",
        placeholder="e.g. What datasets are most used for LLM agent evaluation?",
        key="mem_search_query",
        label_visibility="collapsed",
    )

    example_queries = [
        "fastest-growing topics in RAG",
        "datasets used for multimodal reasoning",
        "limitations in robotics language models",
        "papers combining diffusion and graphs",
        "methods replacing LoRA",
        "saturated benchmarks in NLP",
        "open research gaps in code generation",
        "papers easiest to reproduce",
    ]
    st.caption("Try: " + " · ".join(f"*{q}*" for q in example_queries[:4]))

    mem_type_options = ["All", "summary", "problem", "method", "limitation",
                        "future_work", "claim", "contribution"]
    sel_mem_types = st.multiselect(
        "Memory types to search",
        mem_type_options[1:],
        default=[],
        key="mem_search_types",
    )

    col_s1, col_s2 = st.columns([1, 3])
    with col_s1:
        n_results = st.number_input("Max results", 5, 50, 20, key="mem_search_n")

    if st.button("🔍 Search Memory", use_container_width=False, key="mem_search_btn") or memory_query:
        if memory_query:
            with st.spinner("Searching research memory…"):
                types_filter = sel_mem_types if sel_mem_types else None
                results = _rme2.query_memory(
                    memory_query,
                    memory_types=types_filter,
                    limit=int(n_results),
                )

            st.markdown(f"**{len(results)} results for:** _{memory_query}_")
            st.markdown("---")

            entity_results = [r for r in results if r.get("source") == "entity"]
            semantic_results = [r for r in results if r.get("source") != "entity"]

            if entity_results:
                st.markdown("#### 🔵 Matching Entities in Knowledge Graph")
                for r in entity_results:
                    with st.expander(f"**{r['name']}** ({r['entity_type']}) — freq: {r['frequency']}"):
                        st.write(r.get("description", "_No description_"))
            if semantic_results:
                st.markdown("#### 📝 Matching Research Memory Chunks")
                for r in semantic_results:
                    chip_type = r.get("memory_type", "memory")
                    pid = r.get("paper_id") or r.get("metadata", {}).get("paper_id")
                    with st.expander(f"[{chip_type}] Paper #{pid} — relevance: {r.get('relevance', 0)}"):
                        st.write(r.get("text", ""))

            if not results:
                st.info("No results found. Build the knowledge graph first with the **Build / Update Knowledge Graph** button in the Knowledge Graph tab.")

    st.markdown("---")

    # --- Trending topics panel ---
    st.markdown("### 📈 Currently Trending in Research Memory")
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.markdown("**Methods & Models (7-day velocity)**")
        trending_m = _rme2.get_trending_entities(entity_type="Method", window_days=7, limit=10)
        if trending_m:
            for t in trending_m:
                st.markdown(f"- {t['name']} `v={t['velocity']:.2f}` `sat={t['saturation']:.0%}`")
        else:
            st.caption("No trend data yet.")
    with t_col2:
        st.markdown("**Datasets & Benchmarks**")
        trending_d = _rme2.get_trending_entities(entity_type="Dataset", window_days=7, limit=10)
        if trending_d:
            for t in trending_d:
                st.markdown(f"- {t['name']} `freq={t['total_mentions']}`")
        else:
            st.caption("No trend data yet.")

    st.markdown("---")

    # --- Research gap quick view ---
    st.markdown("### 🕳️ Top Open Research Gaps")
    top_gaps_mem = _rme2.find_research_gaps(limit=8)
    if top_gaps_mem:
        for g in top_gaps_mem:
            st.markdown(
                f"- **{g['name']}** — freq: {g['frequency']} | score: {g['gap_score']} "
                f"| impl: {g.get('implementation_potential', 0):.0%}"
            )
    else:
        st.info("Scan research gaps from the Knowledge Graph tab to populate this panel.")

    st.markdown("---")

    # --- Memory stats ---
    st.markdown("### 🗄️ Research Memory Database")
    s_mem = get_session()
    try:
        from app.database import get_kg_stats
        s_mem_stats = get_kg_stats(s_mem)
    finally:
        s_mem.close()
    ms1, ms2, ms3, ms4 = st.columns(4)
    ms1.metric("Entities", s_mem_stats.get("entities", 0))
    ms2.metric("Relationships", s_mem_stats.get("edges", 0))
    ms3.metric("Semantic Chunks", s_mem_stats.get("semantic_memories", 0))
    ms4.metric("Trend Records", s_mem_stats.get("trend_records", 0))


# ============================================================
# TAB 10: Settings
# ============================================================
with tabs[9]:
    st.header("⚙️ Settings")
    st.markdown("Configure the dashboard. Changes require a `.env` file update and app restart.")

    st.markdown("### 🔑 API Configuration")
    st.code("OPENROUTER_API_KEY=your_key_here", language="bash")
    st.markdown(f"**Current model:** `{os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o-mini')}`")
    st.markdown(f"**API key configured:** {'✅ Yes' if is_api_key_configured() else '❌ No'}")

    st.markdown("---")
    st.markdown("### 📥 arXiv Settings")
    st.markdown(f"**Categories:** `{os.getenv('FETCH_CATEGORIES', 'cs.CL,cs.AI,cs.LG,...')}`")
    st.markdown(f"**Max results per fetch:** `{os.getenv('ARXIV_MAX_RESULTS', '50')}`")

    st.markdown("---")
    st.markdown("### 🤖 LLM Settings")
    st.markdown(f"**Temperature:** `{os.getenv('LLM_TEMPERATURE', '0.2')}`")
    st.markdown(f"**Max tokens:** `{os.getenv('LLM_MAX_TOKENS', '2500')}`")

    st.markdown("---")
    st.markdown("### 💾 Database")
    st.markdown(f"**Database URL:** `{os.getenv('DATABASE_URL', 'sqlite:///data/arxiv_papers.db')}`")

    session = get_session()
    try:
        from app.database import Paper as PaperModel, Summary as SumModel, Report as RepModel, get_kg_stats
        st.markdown(f"**Papers stored:** {session.query(PaperModel).count()}")
        st.markdown(f"**Summaries stored:** {session.query(SumModel).count()}")
        st.markdown(f"**Reports stored:** {session.query(RepModel).count()}")
        _kg = get_kg_stats(session)
        st.markdown(f"**KG entities:** {_kg.get('entities', 0)} | **edges:** {_kg.get('edges', 0)} | **semantic memories:** {_kg.get('semantic_memories', 0)}")
    finally:
        session.close()

    st.markdown("---")
    st.markdown("### 📄 Full PDF Extraction")
    st.markdown(f"**Enabled:** `{os.getenv('ENABLE_FULL_TEXT_EXTRACTION', 'false')}`")
    st.markdown("Set `ENABLE_FULL_TEXT_EXTRACTION=true` in .env to auto-extract PDFs during summarization.")

    st.markdown("---")
    st.markdown("### ⏰ Scheduler")
    st.markdown("""
    To run the daily scheduler as a background process:
    ```bash
    python scripts/run_scheduler.py
    ```
    This fetches 50 papers daily at 6 AM UTC by default.
    Set `SCHEDULER_HOUR` and `SCHEDULER_MINUTE` in .env to customize.
    """)

    st.markdown("---")
    st.markdown("### 🔄 Refresh & Clear Cache")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Clear Data Cache"):
            st.cache_data.clear()
            st.success("Cache cleared!")
    with col_b:
        if st.button("📋 Show .env.example"):
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_example = os.path.join(root, ".env.example")
            if os.path.exists(env_example):
                with open(env_example) as f:
                    st.code(f.read(), language="bash")
