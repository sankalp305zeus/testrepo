FROM python:3.11-slim

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Streamlit — disable browser auto-open and telemetry
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    # Hugging Face — use a writable cache dir inside the container
    HF_HOME=/app/data/hf_cache \
    HF_DATASETS_CACHE=/app/data/hf_cache

WORKDIR /app

# Install dependencies first (cached layer unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY tests/ ./tests/
COPY pytest.ini .

# data/ is mounted at runtime via docker-compose volume (not baked in)
# .env is also mounted at runtime — never baked into the image

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "src/app/streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
