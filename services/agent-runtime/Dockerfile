FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# workspace install: pyproject.toml only first (cache layer), then sources
COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/agent-runtime/pyproject.toml services/agent-runtime/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace --package agent-runtime

COPY libs/ libs/
COPY services/agent-runtime/ services/agent-runtime/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package agent-runtime

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "agent_runtime.worker"]
