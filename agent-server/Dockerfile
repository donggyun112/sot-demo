FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY packages/service-auth /app/packages/service-auth
COPY agent-server/pyproject.toml agent-server/uv.lock /app/agent-server/
COPY agent-server/src /app/agent-server/src

WORKDIR /app/agent-server
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "agent_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
