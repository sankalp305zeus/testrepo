# Deployment Runbook

This document covers how to deploy the AI Restaurant Recommendations app outside a developer laptop. Follow the steps in order; each section builds on the previous one.

**Related docs:** [README.md](../README.md) · [architecture.md](./architecture.md) · [implementation-plan.md](./implementation-plan.md)

---

## 1. Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Local dev / CI |
| Docker | 24+ | Container build |
| Docker Compose | v2 | Local container run |
| Git | any | Source control |
| Groq API key | — | LLM calls — [console.groq.com/keys](https://console.groq.com/keys) |

---

## 2. Local setup (non-Docker)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd testrepo

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure secrets
cp .env.example .env
# Edit .env — set GROQ_API_KEY=gsk_...

# 5. Download and cache the Zomato catalog (once)
python -m src.data.ingest

# 6. Run tests (no API key needed)
pytest

# 7. Start the app
streamlit run src/app/streamlit_app.py
# Open http://localhost:8501
```

---

## 3. Docker (local)

```bash
# Build the image
docker build -t restaurant-recommender .

# First run — ingest catalog (writes to ./data/)
docker compose --profile tools run --rm ingest

# Start the app
docker compose up

# Open http://localhost:8501
```

**Secrets:** Docker Compose reads your local `.env` file via `env_file: .env`. The key is never baked into the image.

**Data persistence:** `./data/` is mounted as a volume so the catalog cache survives container restarts.

To stop:
```bash
docker compose down
```

---

## 4. Cloud deployment options

### Option A — Streamlit Community Cloud (recommended for demos)

**Cost:** Free · **Setup:** ~5 min · **Custom domain:** No

1. Push this repo to a public (or private) GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, branch `main`, and main file `src/app/streamlit_app.py`
4. Under **Advanced settings → Secrets**, add:
   ```toml
   GROQ_API_KEY = "gsk_..."
   GROQ_MODEL = "llama-3.3-70b-versatile"
   ```
5. Click **Deploy**

> **Note:** Streamlit Community Cloud does not persist files between cold starts. The catalog will be re-downloaded on each cold start (~30–60 s). To avoid this, pre-commit `data/restaurants.parquet` to the repo (remove it from `.gitignore` first) or use Option C/D below.

---

### Option B — Hugging Face Spaces

**Cost:** Free · **Setup:** ~10 min · **Custom domain:** No

1. Create a new Space at [huggingface.co/spaces](https://huggingface.co/new-space), SDK = **Docker**
2. Push this repo to the Space (HF Spaces uses a Git remote)
3. Add `GROQ_API_KEY` as a Space secret under **Settings → Variables and secrets**
4. HF will build the `Dockerfile` and expose port 7860; update `docker-compose.yml` port if needed

---

### Option C — Railway / Render

**Cost:** Free tier available · **Setup:** ~15 min · **Custom domain:** Yes

1. Connect your GitHub repo to [railway.app](https://railway.app) or [render.com](https://render.com)
2. Set environment variable `GROQ_API_KEY` in the platform dashboard
3. Set start command: `streamlit run src/app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
4. Add a persistent disk / volume mounted at `/app/data` so the catalog cache survives deploys

---

### Option D — Docker on a VPS

**Cost:** ~$5/mo · **Setup:** ~30 min · **Custom domain:** Yes

```bash
# On the VPS
git clone <repo-url>
cd testrepo
cp .env.example .env
# Edit .env — set GROQ_API_KEY

# Ingest catalog once
docker compose --profile tools run --rm ingest

# Run app in background
docker compose up -d

# (Optional) reverse proxy with nginx or caddy on port 80/443
```

---

## 5. CI/CD — GitHub Actions

The workflow at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on every push and pull request to `main`:

- Installs dependencies
- Runs `pytest` with `MOCK_LLM=1` (no Groq key needed)

**No secrets are required in CI.** Add the CI badge to your README:

```markdown
[![CI](https://github.com/<org>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<org>/<repo>/actions/workflows/ci.yml)
```

---

## 6. Smoke test checklist (post-deploy)

Run through these after every deployment:

| # | Step | Expected |
|---|------|----------|
| 1 | Open the app URL | Page loads, catalog size shown |
| 2 | Check sidebar status | ✅ Catalog · ✅ Groq (key configured) |
| 3 | Submit: Bangalore / medium / North Indian / 4.0 | 3–5 recommendations with explanations |
| 4 | Submit: Tokyo / low / Ethiopian / 5.0 | Friendly empty state with hints |
| 5 | Clear `GROQ_API_KEY`, resubmit | Fallback rankings shown with warning |
| 6 | `pytest` (local or CI) | All tests pass |

---

## 7. Environment variables reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | Yes (for AI) | — | Groq API key |
| `LLM_API_KEY` | No | — | Legacy alias for `GROQ_API_KEY` |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model ID |
| `MOCK_LLM` | No | — | `1` = skip Groq, use rule-based fallback |
| `FORCE_REFRESH_CATALOG` | No | — | `1` = re-download dataset, ignore cache |
| `CACHE_TTL_SECONDS` | No | `300` | Pipeline result cache lifetime (seconds) |
| `DISABLE_CACHE` | No | — | `1` = disable result cache entirely |

---

## 8. Known limitations

- **Dataset coverage** — Only cities in the Hugging Face Zomato dataset (primarily Bangalore). Other cities return an empty shortlist.
- **Cold start** — First run downloads the dataset (~100 MB). Use a pre-built `data/restaurants.parquet` or a persistent volume to avoid this on each deploy.
- **Single-user MVP** — Streamlit runs in a single process; no authentication or multi-tenant support.
- **Groq quota** — Each recommendation request makes one API call. The shortlist cap (≤ 30 rows) keeps token usage low.
- **Budget bands** — `low ≤ ₹400`, `medium ₹401–800`, `high > ₹800` are heuristic; calibrate against actual dataset distribution as needed.
