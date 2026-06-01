.PHONY: test run api ingest mock docker-build docker-up docker-ingest docker-down help

help:               ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?##"}; {printf "  %-16s %s\n", $$1, $$2}'

# ── Local (no Docker) ────────────────────────────────────────────────────────

test:               ## Run all unit tests (mocked LLM, no network required)
	pytest

ingest:             ## Download and cache the Zomato restaurant catalog
	python -m src.data.ingest

run:                ## Start the Streamlit app (requires GROQ_API_KEY in .env)
	streamlit run src/app/streamlit_app.py

mock:               ## Start the Streamlit app in offline mode (no Groq call)
	MOCK_LLM=1 streamlit run src/app/streamlit_app.py

api:                ## Start the FastAPI backend on port 8000 (with auto-reload)
	uvicorn src.api.main:app --reload --port 8000

api-mock:           ## Start the FastAPI backend in offline mode (no Groq call)
	MOCK_LLM=1 uvicorn src.api.main:app --reload --port 8000

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build:       ## Build the Docker image
	docker build -t restaurant-recommender .

docker-ingest:      ## Download catalog inside Docker (run once on a fresh clone)
	docker compose --profile tools run --rm ingest

docker-up:          ## Start the app with Docker Compose (http://localhost:8501)
	docker compose up

docker-down:        ## Stop all Docker Compose services
	docker compose down
