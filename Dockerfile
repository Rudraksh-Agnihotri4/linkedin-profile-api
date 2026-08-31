FROM ghcr.io/astral-sh/uv:0.12.7-python3.12-trixie-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev

COPY src ./src

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn --app-dir src tross_linkedin_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-graceful-shutdown 30"]
