"""SQLite database setup and CRUD operations via SQLAlchemy."""

from __future__ import annotations
import json
import os
import logging
from datetime import datetime, date
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Boolean,
    DateTime, Date, ForeignKey, UniqueConstraint, inspect
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM Table Definitions — Core
# ---------------------------------------------------------------------------

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arxiv_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    authors = Column(Text, default="[]")          # JSON list
    abstract = Column(Text, default="")
    categories = Column(Text, default="[]")       # JSON list
    primary_category = Column(String(32), default="")
    published_date = Column(String(32), default="")
    updated_date = Column(String(32), default="")
    pdf_url = Column(Text, default="")
    arxiv_url = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    summary_json = Column(Text, default="{}")
    one_line_summary = Column(Text, default="")
    problem = Column(Text, default="")
    method = Column(Text, default="")
    main_contribution = Column(Text, default="")
    limitations = Column(Text, default="")
    future_work = Column(Text, default="")
    research_area = Column(String(128), default="")
    novelty_score = Column(Integer, default=5)
    impact_score = Column(Integer, default=5)
    technical_depth_score = Column(Integer, default=5)
    implementation_difficulty_score = Column(Integer, default=5)
    reproducibility_score = Column(Integer, default=5)
    code_generation_potential = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("paper_id", "keyword"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    keyword = Column(String(128), nullable=False)


class TrendTag(Base):
    __tablename__ = "trend_tags"
    __table_args__ = (UniqueConstraint("paper_id", "tag"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    tag = Column(String(128), nullable=False)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(64), default="daily")
    title = Column(Text, default="")
    content_markdown = Column(Text, default="")
    source_paper_ids = Column(Text, default="[]")   # JSON list
    created_at = Column(DateTime, default=datetime.utcnow)


class GeneratedCode(Base):
    __tablename__ = "generated_code"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    code_mode = Column(String(128), default="")
    content_markdown = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyTrend(Base):
    __tablename__ = "daily_trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(16), nullable=False, index=True)
    trend_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# ORM Table Definitions — Knowledge Graph & Memory Layer
# ---------------------------------------------------------------------------

class KGEntity(Base):
    """A canonical entity node in the research knowledge graph."""
    __tablename__ = "kg_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(64), nullable=False, index=True)
    name = Column(Text, nullable=False)
    normalized_name = Column(String(256), nullable=False, index=True)
    description = Column(Text, default="")
    source_paper_ids_json = Column(Text, default="[]")
    first_seen_date = Column(String(16), default="")
    last_seen_date = Column(String(16), default="")
    frequency_count = Column(Integer, default=1)
    confidence_score = Column(Float, default=0.7)
    embedding_vector_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KGEdge(Base):
    """A directed relationship edge between two KG entities."""
    __tablename__ = "kg_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False, index=True)
    relationship_type = Column(String(64), nullable=False, index=True)
    target_entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False, index=True)
    source_paper_id = Column(Integer, ForeignKey("papers.id"), nullable=True, index=True)
    evidence_text = Column(Text, default="")
    confidence_score = Column(Float, default=0.7)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class PaperEntityMention(Base):
    """Tracks which entities are mentioned in which papers."""
    __tablename__ = "paper_entity_mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=False, index=True)
    mention_text = Column(Text, default="")
    section = Column(String(64), default="")
    confidence_score = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)


class SemanticMemory(Base):
    """Stores text chunks with JSON-serialized embeddings for hybrid retrieval."""
    __tablename__ = "semantic_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_type = Column(String(64), nullable=False, index=True)
    source_id = Column(Integer, nullable=True, index=True)
    source_table = Column(String(64), default="")
    text = Column(Text, default="")
    embedding_json = Column(Text, default="[]")   # JSON float list
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class ResearchMemoryEvent(Base):
    """Audit log of memory-layer events for explainability."""
    __tablename__ = "research_memory_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True)
    paper_id = Column(Integer, nullable=True)
    description = Column(Text, default="")
    event_date = Column(String(16), default="")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class TrendMemory(Base):
    """Daily entity-level trend metrics for velocity, saturation, novelty."""
    __tablename__ = "trend_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(16), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(Integer, ForeignKey("kg_entities.id"), nullable=True, index=True)
    count = Column(Integer, default=1)
    velocity_score = Column(Float, default=0.0)    # rate of change
    saturation_score = Column(Float, default=0.0)  # how crowded the space is
    novelty_score = Column(Float, default=0.5)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentMemory(Base):
    """Key-value store for persistent agent-level shared memory."""
    __tablename__ = "agent_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(128), nullable=False, index=True)
    memory_key = Column(String(256), nullable=False, index=True)
    memory_value_json = Column(Text, default="{}")
    source_paper_ids_json = Column(Text, default="[]")
    confidence_score = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════
# v2 Tables — Auth, Personalization, Trust, Alerts, Recommendations
# ═══════════════════════════════════════════════════════════════════════════

class User(Base):
    """Registered user account."""
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    email          = Column(String(256), unique=True, nullable=False, index=True)
    password_hash  = Column(String(256), nullable=False)
    full_name      = Column(String(256), default="")
    is_active      = Column(Boolean, default=True)
    is_admin       = Column(Boolean, default=False)
    demo_code      = Column(String(12), unique=True, nullable=True, index=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at  = Column(DateTime, nullable=True)


class UserProfile(Base):
    """Research interests, preferences, and settings per user."""
    __tablename__ = "user_profiles"

    id                         = Column(Integer, primary_key=True, autoincrement=True)
    user_id                    = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    interests_json             = Column(Text, default="[]")    # e.g. ["LLM Agents","RAG"]
    preferred_categories_json  = Column(Text, default="[]")    # e.g. ["cs.CL","cs.AI"]
    preferred_topics_json      = Column(Text, default="[]")
    ignored_topics_json        = Column(Text, default="[]")
    research_goals_json        = Column(Text, default="[]")
    preferred_conferences_json = Column(Text, default="[]")
    compute_budget             = Column(String(64), default="Single GPU")
    alert_frequency            = Column(String(32), default="daily")
    digest_frequency           = Column(String(32), default="daily")
    # Subscription plan: free | pro | lab | admin
    plan                       = Column(String(32), default="free")
    plan_expires_at            = Column(DateTime, nullable=True)
    created_at                 = Column(DateTime, default=datetime.utcnow)
    updated_at                 = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPaperInteraction(Base):
    """Every action a user takes on a paper (viewed, saved, liked, etc.)."""
    __tablename__ = "user_paper_interactions"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    paper_id         = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    # viewed | read | saved | ignored | liked | disliked | generated_code |
    # generated_report | added_to_collection | clicked_pdf | clicked_arxiv |
    # asked_question | shared
    interaction_type = Column(String(64), nullable=False)
    interaction_value = Column(Float, default=1.0)   # weight for scoring
    metadata_json    = Column(Text, default="{}")
    created_at       = Column(DateTime, default=datetime.utcnow, index=True)


class SavedTopic(Base):
    """Topics/entities a user is watching with optional alert."""
    __tablename__ = "saved_topics"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    topic_name    = Column(String(256), nullable=False)
    entity_id     = Column(Integer, ForeignKey("kg_entities.id"), nullable=True)
    alert_enabled = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class UserCollection(Base):
    """Named collection of papers (reading list, project ideas, etc.)."""
    __tablename__ = "user_collections"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name        = Column(String(256), nullable=False)
    description = Column(Text, default="")
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserCollectionItem(Base):
    """Paper inside a user collection."""
    __tablename__ = "user_collection_items"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("user_collections.id"), nullable=False, index=True)
    paper_id      = Column(Integer, ForeignKey("papers.id"), nullable=False)
    notes         = Column(Text, default="")
    created_at    = Column(DateTime, default=datetime.utcnow)


class AlertRule(Base):
    """Rule that triggers an alert for a user."""
    __tablename__ = "alert_rules"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # topic_spike | paper_match | new_code_available | new_research_gap |
    # new_high_opportunity_paper | weekly_field_change | dataset_saturation
    rule_type             = Column(String(64), nullable=False)
    entity_type           = Column(String(64), nullable=True)
    entity_id             = Column(Integer, nullable=True)
    topic_name            = Column(String(256), nullable=True)
    threshold_json        = Column(Text, default="{}")   # {"min_score": 0.85}
    delivery_channels_json = Column(Text, default='["in_app"]')
    enabled               = Column(Boolean, default=True)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Alert(Base):
    """A triggered alert instance for a user."""
    __tablename__ = "alerts"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    alert_type       = Column(String(64), nullable=False)
    title            = Column(String(512), nullable=False)
    message          = Column(Text, default="")
    paper_ids_json   = Column(Text, default="[]")
    entity_ids_json  = Column(Text, default="[]")
    read_status      = Column(Boolean, default=False)
    delivered_status = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow, index=True)


class EmailDigest(Base):
    """Generated email digest for a user."""
    __tablename__ = "email_digests"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # daily | weekly
    digest_type      = Column(String(32), nullable=False)
    subject          = Column(String(512), default="")
    content_markdown = Column(Text, default="")
    paper_ids_json   = Column(Text, default="[]")
    sent_status      = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    sent_at          = Column(DateTime, nullable=True)


class EvidenceSpan(Base):
    """
    Trust layer — a quote extracted from a paper that backs a summary claim.
    high_confidence | medium_confidence | low_confidence |
    missing_evidence | llm_inferred
    """
    __tablename__ = "evidence_spans"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    paper_id          = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    # problem | method | contribution | datasets | results | limitations |
    # future_work | claims | reproducibility | research_gap
    summary_field     = Column(String(64), nullable=False)
    claim_text        = Column(Text, default="")
    evidence_text     = Column(Text, default="")
    section           = Column(String(128), default="abstract")
    page_number       = Column(Integer, nullable=True)
    source_url        = Column(String(512), default="")
    confidence_score  = Column(Float, default=0.5)
    uncertainty_label = Column(String(32), default="medium_confidence")
    created_at        = Column(DateTime, default=datetime.utcnow)


class RecommendationLog(Base):
    """Record of a recommendation made to a user, with score breakdown."""
    __tablename__ = "recommendation_logs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    paper_id      = Column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    score         = Column(Float, default=0.0)
    reason_json   = Column(Text, default="[]")   # ["Matches RAG interest", "Topic velocity +42%"]
    model_version = Column(String(32), default="v1")
    shown_at      = Column(DateTime, nullable=True)
    clicked       = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)


class FetchQueue(Base):
    """Queue of arxiv paper IDs waiting to be processed."""
    __tablename__ = "paper_fetch_queue"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    arxiv_id        = Column(String(32), unique=True, nullable=False, index=True)
    # queued | fetched | summarized | kg_extracted | failed | skipped_duplicate
    status          = Column(String(32), default="queued", index=True)
    priority        = Column(Integer, default=5)
    source_category = Column(String(32), default="")
    attempt_count   = Column(Integer, default=0)
    last_error      = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Engine / Session Factory
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///data/arxiv_papers.db")
    # Make relative paths work from project root
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url[len("sqlite:///"):]
        if not os.path.isabs(rel):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            abs_path = os.path.join(project_root, rel)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            url = f"sqlite:///{abs_path}"
    return url


def init_engine():
    global _engine, _SessionLocal
    db_url = get_db_url()
    _engine = create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_engine():
    global _engine
    if _engine is None:
        init_engine()
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal()


def create_all_tables():
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("All tables created/verified.")


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def upsert_paper(session: Session, meta: Dict[str, Any]) -> Paper:
    """Insert paper if not exists; return existing otherwise."""
    paper = session.query(Paper).filter_by(arxiv_id=meta["arxiv_id"]).first()
    if paper:
        return paper
    paper = Paper(
        arxiv_id=meta["arxiv_id"],
        title=meta.get("title", ""),
        authors=json.dumps(meta.get("authors", [])),
        abstract=meta.get("abstract", ""),
        categories=json.dumps(meta.get("categories", [])),
        primary_category=meta.get("primary_category", ""),
        published_date=meta.get("published_date", ""),
        updated_date=meta.get("updated_date", ""),
        pdf_url=meta.get("pdf_url", ""),
        arxiv_url=meta.get("arxiv_url", ""),
    )
    session.add(paper)
    session.flush()
    return paper


def upsert_summary(session: Session, paper_id: int, data: Dict[str, Any]) -> Summary:
    summary = session.query(Summary).filter_by(paper_id=paper_id).first()
    if not summary:
        summary = Summary(paper_id=paper_id)
        session.add(summary)

    summary.summary_json = json.dumps(data)
    summary.one_line_summary = data.get("one_line_summary", "")
    summary.problem = data.get("problem", "")
    summary.method = data.get("method", "")
    summary.main_contribution = data.get("main_contribution", "")
    summary.limitations = data.get("limitations", "")
    summary.future_work = data.get("future_work", "")
    summary.research_area = data.get("research_area", "")
    summary.novelty_score = int(data.get("novelty_score", 5))
    summary.impact_score = int(data.get("impact_score", 5))
    summary.technical_depth_score = int(data.get("technical_depth_score", 5))
    summary.implementation_difficulty_score = int(data.get("implementation_difficulty_score", 5))
    summary.reproducibility_score = int(data.get("reproducibility_score", 5))
    summary.code_generation_potential = int(data.get("code_generation_potential", 5))
    session.flush()
    return summary


def upsert_keywords(session: Session, paper_id: int, keywords: List[str]):
    for kw in keywords:
        kw = kw.strip()[:128]
        if not kw:
            continue
        exists = session.query(Keyword).filter_by(paper_id=paper_id, keyword=kw).first()
        if not exists:
            session.add(Keyword(paper_id=paper_id, keyword=kw))


def upsert_trend_tags(session: Session, paper_id: int, tags: List[str]):
    for tag in tags:
        tag = tag.strip()[:128]
        if not tag:
            continue
        exists = session.query(TrendTag).filter_by(paper_id=paper_id, tag=tag).first()
        if not exists:
            session.add(TrendTag(paper_id=paper_id, tag=tag))


def get_papers_with_summaries(session: Session, limit: int = 200, date_str: Optional[str] = None) -> List[Dict]:
    """Return papers joined with summaries as dicts."""
    q = (
        session.query(Paper, Summary)
        .outerjoin(Summary, Paper.id == Summary.paper_id)
    )
    if date_str:
        q = q.filter(Paper.published_date.startswith(date_str))
    q = q.order_by(Paper.created_at.desc()).limit(limit)
    rows = q.all()
    result = []
    for paper, summary in rows:
        d = paper_to_dict(paper)
        if summary:
            d.update(summary_to_dict(summary))
        result.append(d)
    return result


def _safe_json_list(s: str) -> list:
    """Parse a JSON list from a string; handle plain comma-separated strings gracefully."""
    if not s:
        return []
    try:
        val = json.loads(s)
        if isinstance(val, list):
            return val
        return [str(val)]
    except Exception:
        return [a.strip() for a in s.split(",") if a.strip()]


def paper_to_dict(paper: Paper) -> Dict:
    return {
        "id": paper.id,
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": _safe_json_list(paper.authors),
        "abstract": paper.abstract,
        "categories": _safe_json_list(paper.categories),
        "primary_category": paper.primary_category,
        "published_date": paper.published_date,
        "updated_date": paper.updated_date,
        "pdf_url": paper.pdf_url,
        "arxiv_url": paper.arxiv_url,
        "created_at": str(paper.created_at),
    }


def summary_to_dict(summary: Summary) -> Dict:
    raw = {}
    try:
        raw = json.loads(summary.summary_json or "{}")
    except Exception:
        pass
    return {
        "summary_id": summary.id,
        "one_line_summary": summary.one_line_summary,
        "problem": summary.problem,
        "method": summary.method,
        "main_contribution": summary.main_contribution,
        "limitations": summary.limitations,
        "future_work": summary.future_work,
        "research_area": summary.research_area,
        "novelty_score": summary.novelty_score,
        "impact_score": summary.impact_score,
        "technical_depth_score": summary.technical_depth_score,
        "implementation_difficulty_score": summary.implementation_difficulty_score,
        "reproducibility_score": summary.reproducibility_score,
        "code_generation_potential": summary.code_generation_potential,
        "keywords": raw.get("keywords", []),
        "trend_tags": raw.get("trend_tags", []),
        "datasets_or_benchmarks": raw.get("datasets_or_benchmarks", []),
        "results_or_claims": raw.get("results_or_claims", ""),
        "model_architectures": raw.get("model_architectures", []),
        "methods": raw.get("methods", []),
        "metrics": raw.get("metrics", []),
        "baselines": raw.get("baselines", []),
    }


def get_all_keywords(session: Session) -> List[Dict]:
    rows = session.query(Keyword).all()
    return [{"paper_id": r.paper_id, "keyword": r.keyword} for r in rows]


def get_all_trend_tags(session: Session) -> List[Dict]:
    rows = session.query(TrendTag).all()
    return [{"paper_id": r.paper_id, "tag": r.tag} for r in rows]


def save_report(session: Session, report_type: str, title: str, content: str, paper_ids: List[int]) -> Report:
    r = Report(
        report_type=report_type,
        title=title,
        content_markdown=content,
        source_paper_ids=json.dumps(paper_ids),
    )
    session.add(r)
    session.flush()
    return r


def save_generated_code(session: Session, paper_id: int, code_mode: str, content: str) -> GeneratedCode:
    gc = GeneratedCode(paper_id=paper_id, code_mode=code_mode, content_markdown=content)
    session.add(gc)
    session.flush()
    return gc


def get_generated_code(session: Session, paper_id: int, code_mode: str) -> Optional[str]:
    gc = session.query(GeneratedCode).filter_by(paper_id=paper_id, code_mode=code_mode).order_by(GeneratedCode.created_at.desc()).first()
    return gc.content_markdown if gc else None


def save_daily_trend(session: Session, date_str: str, trend_data: Dict):
    dt = DailyTrend(date=date_str, trend_json=json.dumps(trend_data))
    session.add(dt)
    session.flush()
    return dt


def get_stats(session: Session) -> Dict:
    total = session.query(Paper).count()
    summarized = session.query(Summary).count()
    today_str = date.today().isoformat()
    today_count = session.query(Paper).filter(Paper.published_date.startswith(today_str)).count()
    if today_count == 0:
        # Fall back to papers created today
        today_count = session.query(Paper).filter(Paper.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)).count()
    return {"total": total, "summarized": summarized, "today": today_count}


# ---------------------------------------------------------------------------
# Knowledge Graph CRUD helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, strip, collapse spaces — used as dedup key."""
    return " ".join(name.lower().strip().split())


def upsert_kg_entity(
    session: Session,
    entity_type: str,
    name: str,
    description: str = "",
    source_paper_id: Optional[int] = None,
    confidence: float = 0.7,
    metadata: Optional[Dict] = None,
) -> KGEntity:
    """Insert or merge a KG entity. Returns the entity row."""
    norm = _normalize(name)
    today = date.today().isoformat()

    entity = (
        session.query(KGEntity)
        .filter_by(entity_type=entity_type, normalized_name=norm)
        .first()
    )
    if entity:
        entity.frequency_count += 1
        entity.last_seen_date = today
        if description and not entity.description:
            entity.description = description
        if source_paper_id:
            ids = json.loads(entity.source_paper_ids_json or "[]")
            if source_paper_id not in ids:
                ids.append(source_paper_id)
                entity.source_paper_ids_json = json.dumps(ids)
        entity.confidence_score = max(entity.confidence_score, confidence)
        if metadata:
            existing = json.loads(entity.metadata_json or "{}")
            existing.update(metadata)
            entity.metadata_json = json.dumps(existing)
    else:
        entity = KGEntity(
            entity_type=entity_type,
            name=name[:512],
            normalized_name=norm[:256],
            description=description,
            source_paper_ids_json=json.dumps([source_paper_id] if source_paper_id else []),
            first_seen_date=today,
            last_seen_date=today,
            frequency_count=1,
            confidence_score=confidence,
            metadata_json=json.dumps(metadata or {}),
        )
        session.add(entity)

    session.flush()
    return entity


def upsert_kg_edge(
    session: Session,
    source_id: int,
    rel_type: str,
    target_id: int,
    paper_id: Optional[int] = None,
    evidence: str = "",
    confidence: float = 0.7,
) -> KGEdge:
    """Insert an edge if it does not already exist for this paper."""
    existing = (
        session.query(KGEdge)
        .filter_by(source_entity_id=source_id, relationship_type=rel_type, target_entity_id=target_id)
        .first()
    )
    if existing and paper_id and existing.source_paper_id == paper_id:
        return existing
    edge = KGEdge(
        source_entity_id=source_id,
        relationship_type=rel_type,
        target_entity_id=target_id,
        source_paper_id=paper_id,
        evidence_text=evidence[:1000],
        confidence_score=confidence,
    )
    session.add(edge)
    session.flush()
    return edge


def add_paper_entity_mention(
    session: Session,
    paper_id: int,
    entity_id: int,
    mention_text: str = "",
    section: str = "",
    confidence: float = 0.7,
) -> PaperEntityMention:
    m = PaperEntityMention(
        paper_id=paper_id,
        entity_id=entity_id,
        mention_text=mention_text[:500],
        section=section,
        confidence_score=confidence,
    )
    session.add(m)
    session.flush()
    return m


def add_semantic_memory(
    session: Session,
    memory_type: str,
    source_id: int,
    source_table: str,
    text: str,
    embedding: Optional[List[float]] = None,
    metadata: Optional[Dict] = None,
) -> SemanticMemory:
    sm = SemanticMemory(
        memory_type=memory_type,
        source_id=source_id,
        source_table=source_table,
        text=text[:4000],
        embedding_json=json.dumps(embedding or []),
        metadata_json=json.dumps(metadata or {}),
    )
    session.add(sm)
    session.flush()
    return sm


def log_memory_event(
    session: Session,
    event_type: str,
    description: str,
    entity_id: Optional[int] = None,
    paper_id: Optional[int] = None,
    metadata: Optional[Dict] = None,
):
    e = ResearchMemoryEvent(
        event_type=event_type,
        entity_id=entity_id,
        paper_id=paper_id,
        description=description,
        event_date=date.today().isoformat(),
        metadata_json=json.dumps(metadata or {}),
    )
    session.add(e)
    session.flush()
    return e


def upsert_trend_memory(
    session: Session,
    entity_id: int,
    entity_type: str,
    velocity: float = 0.0,
    saturation: float = 0.0,
    novelty: float = 0.5,
):
    today = date.today().isoformat()
    row = (
        session.query(TrendMemory)
        .filter_by(date=today, entity_id=entity_id)
        .first()
    )
    if row:
        row.count += 1
        row.velocity_score = velocity
        row.saturation_score = saturation
        row.novelty_score = novelty
    else:
        row = TrendMemory(
            date=today,
            entity_type=entity_type,
            entity_id=entity_id,
            count=1,
            velocity_score=velocity,
            saturation_score=saturation,
            novelty_score=novelty,
        )
        session.add(row)
    session.flush()
    return row


def upsert_agent_memory(
    session: Session,
    agent_name: str,
    memory_key: str,
    value: Any,
    paper_ids: Optional[List[int]] = None,
    confidence: float = 0.7,
) -> AgentMemory:
    row = session.query(AgentMemory).filter_by(agent_name=agent_name, memory_key=memory_key).first()
    if row:
        row.memory_value_json = json.dumps(value)
        row.source_paper_ids_json = json.dumps(paper_ids or [])
        row.confidence_score = confidence
    else:
        row = AgentMemory(
            agent_name=agent_name,
            memory_key=memory_key,
            memory_value_json=json.dumps(value),
            source_paper_ids_json=json.dumps(paper_ids or []),
            confidence_score=confidence,
        )
        session.add(row)
    session.flush()
    return row


def get_kg_stats(session: Session) -> Dict:
    """Return high-level knowledge graph stats."""
    return {
        "entities": session.query(KGEntity).count(),
        "edges": session.query(KGEdge).count(),
        "mentions": session.query(PaperEntityMention).count(),
        "semantic_memories": session.query(SemanticMemory).count(),
        "trend_records": session.query(TrendMemory).count(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# v2 CRUD helpers
# ═══════════════════════════════════════════════════════════════════════════

def create_user(session: Session, email: str, password_hash: str, full_name: str = "") -> User:
    user = User(email=email.lower().strip(), password_hash=password_hash, full_name=full_name)
    session.add(user)
    session.flush()
    # Auto-create empty profile
    profile = UserProfile(user_id=user.id)
    session.add(profile)
    session.flush()
    return user


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.query(User).filter_by(email=email.lower().strip()).first()


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.query(User).filter_by(id=user_id).first()


def get_or_create_profile(session: Session, user_id: int) -> UserProfile:
    p = session.query(UserProfile).filter_by(user_id=user_id).first()
    if not p:
        p = UserProfile(user_id=user_id)
        session.add(p)
        session.flush()
    return p


# ─── Default alert rules ──────────────────────────────────────────────────────

# Maps the product-facing rule names to the rule_types the AlertAgent evaluates.
DEFAULT_ALERT_RULES = [
    {"rule_type": "paper_match",        "topic_name": None, "threshold": {"min_score": 0.75}},
    {"rule_type": "topic_spike",        "topic_name": None, "threshold": {"min_velocity": 0.35}},
    {"rule_type": "new_research_gap",   "topic_name": None, "threshold": {"min_gap_score": 0.70}},
    {"rule_type": "new_code_available", "topic_name": None, "threshold": {"min_build_score": 8}},
]


def get_unsummarized_paper_ids(session: Session, limit: Optional[int] = None) -> List[int]:
    """Return ids of papers that have no Summary row."""
    summarized = {s.paper_id for s in session.query(Summary.paper_id).all()}
    q = session.query(Paper.id).order_by(Paper.id.desc())
    ids = [pid for (pid,) in q.all() if pid not in summarized]
    return ids[:limit] if limit else ids


def ensure_default_alert_rules_for_user(session: Session, user_id: int) -> int:
    """Create the default alert rule set for a user if they have none. Returns count created."""
    existing = session.query(AlertRule).filter_by(user_id=user_id).count()
    if existing > 0:
        return 0
    created = 0
    for spec in DEFAULT_ALERT_RULES:
        rule = AlertRule(
            user_id=user_id,
            rule_type=spec["rule_type"],
            topic_name=spec["topic_name"],
            threshold_json=json.dumps(spec["threshold"]),
            delivery_channels_json=json.dumps(["in_app"]),
            enabled=True,
        )
        session.add(rule)
        created += 1
    session.flush()
    return created


def ensure_default_alert_rules_for_all_users(session: Session) -> Dict:
    """Backfill default alert rules for every user lacking them."""
    users = session.query(User).all()
    total = 0
    touched = 0
    for u in users:
        n = ensure_default_alert_rules_for_user(session, u.id)
        if n:
            touched += 1
            total += n
    session.commit()
    return {"users_updated": touched, "rules_created": total, "total_users": len(users)}


def log_interaction(
    session: Session,
    user_id: int,
    paper_id: int,
    interaction_type: str,
    value: float = 1.0,
    metadata: Optional[Dict] = None,
) -> UserPaperInteraction:
    row = UserPaperInteraction(
        user_id=user_id,
        paper_id=paper_id,
        interaction_type=interaction_type,
        interaction_value=value,
        metadata_json=json.dumps(metadata or {}),
    )
    session.add(row)
    session.flush()
    return row


def add_evidence_span(
    session: Session,
    paper_id: int,
    summary_field: str,
    claim_text: str,
    evidence_text: str,
    confidence: float = 0.5,
    uncertainty: str = "medium_confidence",
    section: str = "abstract",
) -> EvidenceSpan:
    span = EvidenceSpan(
        paper_id=paper_id,
        summary_field=summary_field,
        claim_text=claim_text,
        evidence_text=evidence_text,
        confidence_score=confidence,
        uncertainty_label=uncertainty,
        section=section,
    )
    session.add(span)
    session.flush()
    return span


def get_evidence_for_paper(session: Session, paper_id: int) -> List[Dict]:
    spans = session.query(EvidenceSpan).filter_by(paper_id=paper_id).all()
    return [
        {
            "field": s.summary_field,
            "claim": s.claim_text,
            "evidence": s.evidence_text,
            "section": s.section,
            "confidence": s.confidence_score,
            "uncertainty": s.uncertainty_label,
        }
        for s in spans
    ]


def enqueue_arxiv_id(session: Session, arxiv_id: str, category: str = "", priority: int = 5) -> FetchQueue:
    existing = session.query(FetchQueue).filter_by(arxiv_id=arxiv_id).first()
    if existing:
        return existing
    row = FetchQueue(arxiv_id=arxiv_id, source_category=category, priority=priority)
    session.add(row)
    session.flush()
    return row


def get_queue_stats(session: Session) -> Dict:
    from sqlalchemy import func
    counts = {}
    for status in ("queued", "fetched", "summarized", "kg_extracted", "failed", "skipped_duplicate"):
        counts[status] = session.query(FetchQueue).filter_by(status=status).count()
    counts["total"] = session.query(FetchQueue).count()
    return counts


def get_recommendation_feed(
    session: Session,
    user_id: int,
    limit: int = 20,
) -> List[Dict]:
    """Return latest recommendation log entries for a user with paper data."""
    rows = (
        session.query(RecommendationLog)
        .filter_by(user_id=user_id)
        .order_by(RecommendationLog.score.desc())
        .limit(limit)
        .all()
    )
    result = []
    for r in rows:
        paper = session.query(Paper).filter_by(id=r.paper_id).first()
        if paper:
            result.append({
                "paper_id": r.paper_id,
                "score": r.score,
                "reasons": json.loads(r.reason_json or "[]"),
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
            })
    return result


def get_user_alerts(session: Session, user_id: int, unread_only: bool = False, limit: int = 50) -> List[Dict]:
    q = session.query(Alert).filter_by(user_id=user_id)
    if unread_only:
        q = q.filter_by(read_status=False)
    alerts_rows = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "type": a.alert_type,
            "title": a.title,
            "message": a.message,
            "read": a.read_status,
            "created_at": str(a.created_at)[:19],
        }
        for a in alerts_rows
    ]
