# SmartEstate AI — API + automation worker image (one container: uvicorn plus the worker as a second process).
# Build context: apps/api.  docker build -t smartestate-api apps/api
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Mirror the repository layout (apps/api) so the app's repository-relative paths resolve as they do locally.
WORKDIR /srv/apps/api

# Dependencies first (better layer caching), then the headless Chromium used for brochure PDFs and poster PNGs.
COPY pyproject.toml ./
COPY app ./app
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --upgrade pip && pip install . \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

COPY alembic.ini ./
COPY alembic ./alembic
COPY deploy ./deploy

# Runtime folders for uploaded media and 3D models (ephemeral on free hosting — see docs/DEPLOYMENT.md).
RUN mkdir -p var/media var/models && useradd --create-home --uid 10001 app && chown -R app:app /srv /ms-playwright
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
