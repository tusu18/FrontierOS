# FrontierOS — Research Intelligence Terminal

FrontierOS fetches, summarizes, and connects CS arXiv papers into a shared
research-memory knowledge graph, then surfaces personalized recommendations,
trend spikes, research gaps, evidence-backed summaries, and paper-to-code
scaffolding. It runs as a single FastAPI process that also serves a React
single-page app (no build step — JSX is compiled in-browser via Babel).

---

## Active architecture

- **Single process:** FastAPI (`app/api/server.py`) serves the JSON API *and*
  the static React SPA.
- **Frontend:** static React SPA in `static/` (`app.html` + `app/*.jsx`),
  compiled in the browser with Babel standalone. **No frontend build step.**
- **Database:** SQLite by default (`data/arxiv_papers.db`). Postgres supported
  via `DATABASE_URL` (see below).
- **Agents:** specialized agents in `app/agents/`, coordinated by a central
  orchestrator (`app/agents/orchestrator.py`) with an APScheduler loop.
- **Global memory:** knowledge graph tables (`kg_entities`, `kg_edges`,
  `trend_memory`, `semantic_memory`, `evidence_spans`).
- **Personal memory:**
  - Browser-local graph via Dexie/IndexedDB (`static/app/personalGraph.js`) —
    private by default; only a compact context is sent to agents.
  - Server-side per-user interactions (`user_paper_interactions`) plus optional
    Mem0 (local / qdrant / disabled).

```
arxiv-cs-agent-dashboard/
├── run.py                       # Entry point → uvicorn app.api.server:app
├── app/
│   ├── api/server.py            # FastAPI app + all routes (active backend)
│   ├── agents/                  # Summarizer, evidence, KG, recommendation, alert, orchestrator
│   ├── engines/                 # PersonalizationEngine (Mem0 bridge)
│   ├── memory/                  # ResearchMemoryEngine (global KG + semantic memory)
│   ├── database.py              # SQLAlchemy ORM + helpers
│   ├── email_sender.py          # SMTP access-code email (graceful fallback)
│   └── auth.py                  # JWT auth + password hashing
├── static/
│   ├── app.html                 # SPA shell (loads React, Dexie, data.js, JSX)
│   ├── index.html               # Marketing landing page
│   └── app/                     # *.jsx components + data.js + personalGraph.js
├── scripts/                     # bootstrap, validation, audit, db-check
└── archive/legacy/              # Archived legacy Streamlit UI + old api.py/frontend
```

> Legacy note: the old Streamlit dashboard (`app/dashboard.py`) and the previous
> `api.py` + `frontend/` server are archived under `archive/legacy/`. The active
> UI is the static React SPA served by FastAPI.

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in OPENROUTER_API_KEY
python run.py                 # http://localhost:8000/app
```

- Dashboard: http://localhost:8000/app
- Landing: http://localhost:8000/
- API docs: http://localhost:8000/api/docs

### FrontierOS design exports

Bundled HTML exports live in `design/`. Rebuild the marketing landing and sync
terminal styles (fonts loaded from Google Fonts in `app.html`):

```bash
python scripts/build_frontier_landing.py
python scripts/build_frontier_terminal.py
```

`static/index.html` is the unpacked FrontierOS landing (exact layout) with the
signup form wired to `POST /auth/request-demo`.

### Access (invite-only beta)
The dashboard is gated — you cannot enter without authenticating. Sign up,
sign in, or enter an emailed access code. Admin accounts are configured by
email in the backend.

---

## Bootstrap the MVP

After fetching papers, run the repair/bootstrap pipeline to summarize the
backlog, extract evidence + KG, create default alert rules, and generate
recommendations and alerts:

```bash
python scripts/bootstrap_mvp.py --limit 25     # process up to 25 pending papers
python scripts/bootstrap_mvp.py --all          # process all pending papers
python scripts/bootstrap_mvp.py --skip-llm     # rules/recs/alerts only, no LLM
```

You can also process pending papers from **Admin → Process Pending Papers**.

---

## Configuration

### SMTP (access-code email)
Set the SMTP variables in `.env`. If they are missing or rejected, signup never
fails — the access code is shown directly in the UI as a beta fallback.

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-char-app-password   # Gmail requires 2-Step Verification
SMTP_FROM=ResearchRadar <you@gmail.com>
```

Test/inspect SMTP status in **Admin → System Health**.

### Personal memory (Mem0)
```
MEMORY_BACKEND=local      # local | qdrant | disabled
MEMORY_STRICT=false       # if true, qdrant failure does NOT fall back to local
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=researchradar_mem0
```
- `local` — DB-only by default (no external vector DB).
- `qdrant` — start Qdrant (`docker compose up -d qdrant`) and set the env. Mem0
  embeddings require a real OpenAI-compatible key (`OPENAI_API_KEY`).
- `disabled` — skip Mem0; rely on DB interactions + browser graph.

### Memory search mode
```
ENABLE_LOCAL_EMBEDDINGS=false   # false → keyword/hybrid-lite, true → embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```
The Research Memory page shows the active mode ("keyword/hybrid-lite" or
"semantic embeddings").

### Database (SQLite default, Postgres optional)
```
DATABASE_URL=sqlite:///data/arxiv_papers.db
# Production:
# DATABASE_URL=postgresql+psycopg2://researchradar:researchradar@localhost:5432/researchradar
```
Start Postgres with `docker compose up -d postgres`. Check the active backend:
```bash
python scripts/check_db_backend.py
```

---

## Validation

```bash
python scripts/test_mvp_health.py        # DB, tables, admin, integrations
python scripts/test_deduplication.py     # duplicate arxiv_id is not re-inserted
python scripts/test_alert_rules.py       # default rules + AlertAgent runs
# Manual browser test for the personal graph:
#   scripts/test_personal_graph_manual.md
python scripts/audit_legacy_files.py     # report dead files (--archive to move)
```

---

## MVP limitations (acceptable for beta)

- SQLite database (fine for beta; Postgres path documented above).
- SMTP optional — when unconfigured/rejected, the access code is shown in the UI.
- Mem0 personal memory defaults to DB-only local mode.
- Memory search defaults to keyword/hybrid-lite (full embeddings optional).
- The browser-local personal graph is per-device (no cloud sync yet).
