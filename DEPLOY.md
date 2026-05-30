# Deploy FrontierOS API (FastAPI)

GitHub Pages only hosts the **landing**. Signup, email codes, and `/app` need this API running on a public URL.

Recommended host: **[Render](https://render.com)** (free tier; no persistent disk — see notes below).

## 1. Deploy on Render (Blueprint)

1. Push this repo to GitHub (`tusu18/FrontierOS`).
2. Open [Render Dashboard → Blueprints](https://dashboard.render.com/blueprints).
3. **New Blueprint Instance** → connect **FrontierOS** → **Apply**.
4. When prompted, set **Environment Variables** (required):

   | Key | Value |
   |-----|--------|
   | `OPENROUTER_API_KEY` | Your OpenRouter key |
   | `APP_BASE_URL` | `https://frontieros-api.onrender.com` (use your actual Render URL) |
   | `RESEND_API_KEY` | **Required on Render free** — [Resend](https://resend.com) API key (SMTP ports are blocked on free tier) |
   | `EMAIL_FROM` | `FrontierOS <tsingh98@umd.edu>` — must be verified in Resend |
   | `SMTP_USER` | Optional if using Resend only; for local dev / paid Render |
   | `SMTP_PASSWORD` | Gmail app password (16 chars, no spaces) — **does not work on Render free** |
   | `SMTP_FROM` | `FrontierOS <tsingh98@umd.edu>` |

5. Wait for deploy (~5–10 min first build). Copy the service URL, e.g.  
   `https://frontieros-api-xxxx.onrender.com`

6. Smoke test:
   - `https://YOUR-URL/api/health` → `{"ok":true,...}`
   - `https://YOUR-URL/` → landing
   - `https://YOUR-URL/app` → dashboard

## 2. Wire GitHub Pages to the API

Repo → **Settings → Secrets and variables → Actions → Variables**:

| Variable | Example |
|----------|---------|
| `FRONTIEROS_API` | `https://frontieros-api-xxxx.onrender.com` |
| `FRONTIEROS_APP` | `https://frontieros-api-xxxx.onrender.com/app` |

Re-run **Actions → Deploy landing to GitHub Pages**.

Landing: `https://tusu18.github.io/FrontierOS/`

## 3. Docker / local production test

```bash
docker build -t frontieros-api .
docker run --rm -p 8000:8000 --env-file .env -v "$(pwd)/data:/app/data" frontieros-api
```

## 4. Optional env vars

| Variable | Default (Render) | Notes |
|----------|------------------|--------|
| `ENABLE_SCHEDULER` | `false` | Set `true` to run daily arXiv fetch on the server |
| `MEMORY_BACKEND` | `disabled` | Use `qdrant` only if you add a Qdrant service |
| `DATABASE_URL` | `sqlite:///data/arxiv_papers.db` | Postgres URL supported; use Render Postgres add-on |

## 5. Email on Render free tier

Render **blocks outbound SMTP** (ports 25, 465, 587) on free web services. Gmail app passwords are correct but connections fail with `Network is unreachable`.

**Fix (recommended):** use [Resend](https://resend.com) over HTTPS:

1. Create a Resend account → **API Keys** → copy `re_...`
2. **Domains** or **Emails** → verify `tsingh98@umd.edu` (or your sending address)
3. In Render env: `RESEND_API_KEY`, `EMAIL_FROM=FrontierOS <tsingh98@umd.edu>`
4. Redeploy → check `GET /api/health/smtp` → `"transport":"resend"`

**Alternative:** upgrade the Render web service to **Starter** ($7/mo) — then Gmail SMTP works with `SMTP_*` vars.

**Alternative (uses your Gmail, no Render change):** [EmailJS](https://www.emailjs.com) from the landing page.

**Full step-by-step:** [docs/EMAILJS_SETUP.md](docs/EMAILJS_SETUP.md)  
**Template HTML:** [docs/EMAILJS_TEMPLATE.html](docs/EMAILJS_TEMPLATE.html)

When the API cannot SMTP-send, the landing page sends the code via EmailJS automatically.

## 6. Free tier notes

- Render free services **sleep** after ~15 min idle; first request may take ~30s.
- **No persistent disk on free tier** — the default SQLite DB is ephemeral (cleared on redeploy/restart). Signup, access codes, and email still work; paper/KG data is not kept long-term unless you add Postgres.
- **Persistent data options:**
  - Upgrade the web service to **Starter** and add a disk in the Render dashboard (`/app/data`), or
  - Use free **[Neon](https://neon.tech)** Postgres and set `DATABASE_URL` to the connection string in Render env vars.

## 7. If Blueprint failed on “disks not supported”

Pull the latest `main` (disk block removed from `render.yaml`) and run **Blueprint → Apply** again.
