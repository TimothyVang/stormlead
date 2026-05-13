FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
COPY services/voice-bridge/pyproject.toml services/voice-bridge/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace --package voice-bridge

COPY services/voice-bridge/ services/voice-bridge/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --package voice-bridge

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "voice_bridge.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
