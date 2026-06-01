# AI Restaurant Recommendations (Zomato use case)

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

AI-powered restaurant recommendation system. Enter your location, budget, cuisine, and rating preferences — the system filters the Zomato catalog and uses **Groq** to rank matches with personalised explanations.

Built by Sankalp. See the docs for full details:

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | Layers, components, data flow |
| [`docs/context.md`](docs/context.md) | Workflow and output fields |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | Phase-wise delivery plan |
| [`docs/edge-cases.md`](docs/edge-cases.md) | Edge cases and handling |
| [`docs/deployment.md`](docs/deployment.md) | Docker, cloud deploy, runbook |

**Dataset:** [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) (Hugging Face, open license).

---

## Quick start

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in your Groq key
cp .env.example .env
# Edit .env → set GROQ_API_KEY=gsk_...
# Get a free key at https://console.groq.com/keys

# 4. Run the app
streamlit run src/app/streamlit_app.py
```

Offline / CI demo (no Groq API call):

```bash
MOCK_LLM=1 streamlit run src/app/streamlit_app.py
```

<!-- Screenshot: add docs/images/streamlit-demo.png after capturing the UI -->

---

## Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes (for AI) | Groq API key — [console.groq.com/keys](https://console.groq.com/keys) |
| `GROQ_MODEL` | No | Override model (default: `llama-3.3-70b-versatile`) |
| `MOCK_LLM` | No | Set to `1` to skip Groq and use rule-based fallback |
| `FORCE_REFRESH_CATALOG` | No | Set to `1` to re-download the Zomato dataset |

---

## Docker quick start

```bash
cp .env.example .env          # add GROQ_API_KEY
docker compose --profile tools run --rm ingest   # download catalog once
docker compose up             # open http://localhost:8501
```

See [`docs/deployment.md`](docs/deployment.md) for cloud deployment (Streamlit Cloud, HF Spaces, Railway, VPS).

---

## How it works

```
User preferences → Filter catalog → Groq LLM → Ranked recommendations
```

1. **Data** — Downloads [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) from Hugging Face on first run; cached under `data/` (gitignored).
2. **Filter** — Deterministic rules: location (case-insensitive), cuisine (substring), rating ≥ min, budget band.
3. **Groq** — LLM ranks the shortlist, picks top results, and writes a 1-2 sentence explanation per pick.
4. **Fallback** — If Groq is unavailable, shows top matches ranked by rating with a template explanation.

**Budget bands** (cost for two, INR): **low** ≤ ₹400 · **medium** ₹401–800 · **high** > ₹800

---

## CLI tools (optional)

Load / inspect the catalog:

```bash
python -m src.data.ingest
```

Filter only (no LLM):

```bash
python -m src.filter.run --location Bangalore --budget medium \
    --cuisine "North Indian" --min-rating 4.0
```

Recommendations via CLI:

```bash
python -m src.recommendation.run --location Bangalore --budget medium \
    --cuisine "North Indian" --min-rating 4.0

# Offline mode
MOCK_LLM=1 python -m src.recommendation.run --location Bangalore \
    --budget medium --cuisine Italian --min-rating 4.0
```

---

## Tests

```bash
pytest          # all unit tests — no network, no GROQ_API_KEY needed
```

Or via Make:

```bash
make test
make ingest     # download + cache the catalog
make run        # start the Streamlit app
make mock       # start the app in offline / MOCK_LLM=1 mode
```

### Smoke test checklist

Run through these manually before each demo:

| # | Step | Expected |
|---|------|----------|
| 1 | `pip install -r requirements.txt` and set `GROQ_API_KEY` in `.env` | No install errors |
| 2 | `make ingest` (first run) | Catalog stats logged; `data/restaurants.parquet` created |
| 3 | Submit typical prefs (Bangalore / medium / North Indian / 4.0) | 3–5 recommendations with explanations |
| 4 | Submit impossible prefs (rating 5.0 + low budget + obscure cuisine) | Friendly empty state with suggestions |
| 5 | Set `MOCK_LLM=1` or clear `GROQ_API_KEY` then submit | Fallback rankings shown with warning |
| 6 | `make test` | All tests pass |

---

## Project layout

```
src/
  app/
    streamlit_app.py     # Phase 4 — Streamlit UI
    forms.py             # Form validation helpers
  models/
    restaurant.py        # Restaurant dataclass
    preferences.py       # UserPreferences dataclass
    recommendation.py    # Recommendation dataclass
  data/
    ingest.py            # Phase 1 — HF dataset load + cache
  filter/
    engine.py            # Phase 2 — deterministic shortlist filter
  llm/
    client.py            # Phase 3 — GroqClient + LLMClient interface
    prompts.py           # Phase 3 — prompt templates
  recommendation/
    engine.py            # Phase 3 — LLM orchestration + fallback
    run.py               # Phase 3 — CLI entry point
docs/
  architecture.md
  context.md
  implementation-plan.md
  edge-cases.md
```

---

## Limitations

- Recommendations are limited to cities present in the Hugging Face Zomato dataset (primarily Bangalore).
- Budget bands are heuristic; calibrate against dataset cost distribution as needed.
- Each Groq request counts against your API quota; the shortlist cap (≤ 30 rows) keeps token usage low.
- MVP is single-user local; no authentication or multi-tenant support.
