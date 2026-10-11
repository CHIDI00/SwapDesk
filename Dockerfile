FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached unless the lock changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself.
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Starts the web API and the queue worker together (shared SQLite state).
# Render injects $PORT; the entrypoint falls back to 8000 locally.
CMD ["bash", "docker-entrypoint.sh"]
