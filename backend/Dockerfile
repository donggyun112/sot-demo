FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY migrations ./migrations

EXPOSE 8000
# Run `docker compose run --rm backend sot-migrate` once before starting web replicas.
CMD ["uvicorn", "sot.main:app", "--host", "0.0.0.0", "--port", "8000"]
