# AI PM Workspace

AI-powered restaurant recommendation system (Zomato use case). See [docs/](docs/) for architecture and implementation plan.

Built by Sankalp.

## Setup (Python 3.9+)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add your Groq key: https://console.groq.com/keys
```

## Phase 4 — Streamlit app (recommended)

```bash
# Live Groq recommendations
streamlit run src/app/streamlit_app.py

# Offline demo (no API call)
MOCK_LLM=1 streamlit run src/app/streamlit_app.py
```

Set in `.env`:

- `GROQ_API_KEY` — required for AI explanations
- `GROQ_MODEL` — optional (default: `llama-3.3-70b-versatile`)
- `MOCK_LLM=1` — rule-based fallback only

<!-- Screenshot: add docs/images/streamlit-demo.png after capturing the UI -->

## Phase 1 — Load restaurant catalog

First run downloads the [Zomato dataset](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) and caches normalized data under `data/` (gitignored).

```bash
python -m src.data.ingest
```

## Phase 2 — Filter catalog (CLI)

```bash
python -m src.filter.run --location Bangalore --budget medium --cuisine "North Indian" --min-rating 4.0
```

Budget bands (cost for two, INR): **low** ≤400 · **medium** 401–800 · **high** &gt;800.

## Phase 3 — Recommendations (CLI)

```bash
python -m src.recommendation.run --location Bangalore --budget medium --cuisine "North Indian" --min-rating 4.0
MOCK_LLM=1 python -m src.recommendation.run --location Bangalore --budget medium --cuisine Italian --min-rating 4.0
```

## Tests

```bash
pytest
```

## Project layout

```
src/
  app/streamlit_app.py     # Phase 4 UI
  app/forms.py             # form validation
  models/                  # Restaurant, UserPreferences, Recommendation
  data/ingest.py
  filter/engine.py
  llm/client.py            # GroqClient
  recommendation/engine.py
docs/
```
