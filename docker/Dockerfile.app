# Judex App Service - Lightweight API container (no ML models)
# Designed for Cloud Run CPU instances, fast startup, scales to 0
FROM python:3.11-slim

WORKDIR /app

# Install minimal system dependencies (no ML libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TEMP_DIR=/tmp/judex \
    USE_MODEL_SERVICE=true \
    PORT=8080

# Create temp directory
RUN mkdir -p /tmp/judex

# Copy requirements and install (filtered for app-only dependencies)
COPY requirements-app.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (no models directory needed)
COPY app/ ./app/

# Expose port (Cloud Run uses PORT env var)
EXPOSE 8080

# Fast health check (no model loading)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os; import urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8080)}/v1/health', timeout=5)" || exit 1

# Run the application - use shell form to expand PORT env var
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
