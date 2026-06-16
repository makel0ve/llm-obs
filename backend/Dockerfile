FROM python:3.11-slim as base
WORKDIR /app
COPY pyproject.toml .

FROM base as production
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir .
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
RUN adduser --system --group appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

FROM base as development
COPY . .
RUN pip install --no-cache-dir -e ".[test]"
