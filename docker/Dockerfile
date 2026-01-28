# SafeVid - Child Safety Video Analysis Service
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
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf/transformers \
    TEMP_DIR=/tmp/safevid

# Create directories
RUN mkdir -p /models/hf /models/hf/transformers /tmp/safevid

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

# Expose port
EXPOSE 8000

# Health check
# Health check with longer timeout for video processing
# The server may be busy processing and slow to respond
# Healthcheck using Python (curl not installed)
HEALTHCHECK --interval=60s --timeout=30s --start-period=180s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health', timeout=10)" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
