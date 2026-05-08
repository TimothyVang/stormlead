FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
COPY apps/buyer-portal/pyproject.toml apps/buyer-portal/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package stormlead-buyer-portal

COPY apps/buyer-portal/ apps/buyer-portal/

WORKDIR /app/apps/buyer-portal
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
