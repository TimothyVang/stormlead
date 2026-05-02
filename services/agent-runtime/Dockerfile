FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# nodejs 20 for the claude-code cli — the agent sdk shells out to it on
# the oauth path (CLAUDE_CODE_OAUTH_TOKEN). see
# docs/research/2026-05-agent-auth-patterns.md.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

# workspace install: pyproject.toml only first (cache layer), then sources
COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/agent-runtime/pyproject.toml services/agent-runtime/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --package agent-runtime

COPY libs/ libs/
COPY services/agent-runtime/ services/agent-runtime/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package agent-runtime

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "agent_runtime.worker"]
