# Judex - Video Evaluation Framework
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
# PYTHONPATH must include /app for imports to work
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf/transformers \
    TEMP_DIR=/tmp/judex \
    PORT=8080 \
    PRELOAD_MODELS=false \
    SKIP_DB_INIT=true \
    SKIP_STORAGE_INIT=true

# Create directories
RUN mkdir -p /models/hf /models/hf/transformers /tmp/judex

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Prefetch models during build (recommended for faster startup)
# This downloads ~1.5GB of models but ensures fast first request
RUN python scripts/prefetch_models.py || echo "Model prefetch completed with warnings"

# Expose port (Cloud Run uses PORT env var, default 8080)
EXPOSE 8080

# Health check - use PORT env var
HEALTHCHECK --interval=60s --timeout=30s --start-period=180s --retries=5 \
    CMD python -c "import os; import urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8080)}/v1/health', timeout=10)" || exit 1

# Run the application - use shell form to expand PORT env var
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
