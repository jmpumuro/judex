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
    TEMP_DIR=/tmp/judex \
    USE_MODEL_SERVICE=true

# Create temp directory
RUN mkdir -p /tmp/judex

# Copy requirements and install (filtered for app-only dependencies)
COPY requirements-app.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (no models directory needed)
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Fast health check (no model loading)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health', timeout=5)" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
