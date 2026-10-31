# ==============================================================================
# Civic Pulse Backend — Production Dockerfile
# Python 3.11-slim with OCR (Tesseract), FFmpeg, libpq, and Playwright Chromium
# ==============================================================================

FROM python:3.11-slim

LABEL maintainer="Civic Pulse Core Team"
LABEL description="Civic Pulse FastAPI Application & Celery Worker Container"

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 1. Install system runtime dependencies:
#    - gcc & libpq-dev (PostgreSQL C extensions)
#    - curl (Healthchecks and downloads)
#    - ffmpeg (Audio/Video transcoding for TTS & Media forensics)
#    - tesseract-ocr (Multilingual document text extraction)
#    - Playwright Chromium headless browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    make \
    libpq-dev \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 3. Copy project definition and install dependencies for layer caching
COPY pyproject.toml README.md /app/
RUN mkdir -p /app/app && touch /app/app/__init__.py && \
    pip install --no-cache-dir .

# 4. Install Playwright Chromium headless browser binaries
RUN mkdir -p /ms-playwright && \
    playwright install chromium && \
    chmod -R 777 /ms-playwright

# 5. Copy full application source code
COPY . /app/

# Re-install package in editable/live mode so modules are linked
RUN pip install --no-cache-dir --no-deps -e .

# 6. Expose default FastAPI API port
EXPOSE 8000

# 7. Default container entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

