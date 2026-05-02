FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# geopandas needs gdal binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./
COPY libs/stormlead_core/pyproject.toml libs/stormlead_core/
COPY libs/stormlead_db/pyproject.toml libs/stormlead_db/
COPY services/storm-watcher/pyproject.toml services/storm-watcher/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-workspace --package storm-watcher

COPY libs/ libs/
COPY services/storm-watcher/ services/storm-watcher/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package storm-watcher

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "storm_watcher.worker"]
