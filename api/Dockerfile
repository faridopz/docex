# DOCex API container.
#
# Used by docker-compose for local dev and by Railway / Fly.io / Render
# for production. Multi-stage isn't worth it here — the image is small.
#
# Building: docker build -f api/Dockerfile -t docex-api .
# Running locally: docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... docex-api

FROM python:3.11-slim

# pdfplumber needs poppler-utils for layout extraction on some PDFs;
# python-docx is pure Python and needs nothing extra.
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so they're cached when only app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app. Railway/Fly will respect .dockerignore (web/, .venv/, etc.).
COPY . .

# Ensure the persistent dirs exist inside the container. In production,
# the deployment platform should mount a volume here so data survives
# restarts. Locally, docker-compose mounts the project root.
RUN mkdir -p /app/rulebooks /app/checks

# Railway sets PORT at runtime; default to 8000 for everywhere else.
ENV PORT=8000
EXPOSE 8000

# Use sh -c so ${PORT} expands at runtime, not build time.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
