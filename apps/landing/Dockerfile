FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY apps/landing/pyproject.toml apps/landing/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace --package stormlead-landing

COPY libs/stormlead_core/ libs/stormlead_core/
COPY apps/landing/ apps/landing/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package stormlead-landing

WORKDIR /app/apps/landing
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
