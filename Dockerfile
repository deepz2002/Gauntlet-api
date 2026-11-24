FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system gauntlet \
    && useradd --system --gid gauntlet --no-create-home gauntlet

COPY --chown=gauntlet:gauntlet app ./app
COPY --chown=gauntlet:gauntlet data ./data
COPY --chown=gauntlet:gauntlet migrations ./migrations
COPY --chown=gauntlet:gauntlet alembic.ini ./

USER gauntlet
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["python", "-m", "app.start"]
