FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/form-receiver/pyproject.toml services/form-receiver/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --package form-receiver

COPY libs/ libs/
COPY services/form-receiver/ services/form-receiver/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package form-receiver

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "form_receiver.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
