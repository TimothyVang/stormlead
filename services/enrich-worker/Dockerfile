FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/enrich-worker/pyproject.toml services/enrich-worker/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace --package enrich-worker

COPY libs/ libs/
COPY services/enrich-worker/ services/enrich-worker/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package enrich-worker

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "enrich_worker.worker"]
