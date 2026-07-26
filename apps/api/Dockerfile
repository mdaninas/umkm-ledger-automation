FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.8
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --frozen --no-dev

COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app

RUN addgroup --system app \
    && adduser --system --ingroup app --no-create-home app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
