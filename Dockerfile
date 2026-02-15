FROM python:3.12-slim AS base

LABEL maintainer="Benjamin Poppe"
LABEL description="Media Library — automated digital media library with web interface"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mediainfo \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r medialibrary && useradd -r -g medialibrary -m medialibrary

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir yt-dlp trafilatura feedparser

# Copy application code
COPY config.json ./
COPY src/ ./src/

# Create directories for data and logs
RUN mkdir -p /media/data /data/metadata /data/logs && chown -R medialibrary:medialibrary /app /data /media

USER medialibrary

# Default environment
ENV MEDIA_ROOT=/media \
    FLASK_SECRET_KEY="" \
    ALLOW_UNSAFE_WERKZEUG=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8096

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8096/ || exit 1

# Run in server mode (web + content downloads — no disc monitoring)
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--mode", "server"]
