FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# layer 1: workspace metadata only (max cache reuse)
COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/ping-post/pyproject.toml services/ping-post/

# layer 2: install deps without sources
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace --package ping-post

# layer 3: copy sources and install workspace
COPY libs/ libs/
COPY services/ping-post/ services/ping-post/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package ping-post

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "ping_post.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
