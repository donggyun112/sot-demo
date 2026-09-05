FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY migrations ./migrations

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "sot.main:app", "--host", "0.0.0.0", "--port", "8000"]
