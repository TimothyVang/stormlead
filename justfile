# stormlead justfile
# install just: cargo install just OR brew install just OR apt install just
# run: just <target>

set dotenv-load

# default target: show help
default:
    @just --list

# --- dev stack ---

# bring up the wsl2 dev stack
up:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml up -d
    @echo "stack up. langfuse: http://localhost:3001  hatchet: http://localhost:8080  litellm: http://localhost:4000"

# tear it down
down:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml down

# nuke volumes too (destructive, dev only)
nuke:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml down -v

# tail logs for one service
logs SERVICE:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml logs -f {{SERVICE}}

# psql into the db
psql:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml exec postgres psql -U stormlead -d stormlead

# --- migrations + seed ---

migrate:
    cd libs/stormlead_db && uv run alembic upgrade head

migrate-rev MSG:
    cd libs/stormlead_db && uv run alembic revision --autogenerate -m "{{MSG}}"

seed:
    uv run python scripts/seed_dev.py

# --- tests ---

test:
    uv run pytest -x -q services libs

test-watch:
    uv run pytest-watch -- -x -q services libs

# --- smoke test: real lead → ping-post → buyer ---
smoke:
    uv run python scripts/smoke_e2e.py

# --- lint + format ---

fmt:
    uv run ruff format services libs
    uv run ruff check --fix services libs

lint:
    uv run ruff check services libs
    uv run mypy services libs

# --- ops ---

backup:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml exec postgres \
        pg_dump -U stormlead stormlead | gzip > backups/dev-$(date +%Y%m%d-%H%M%S).sql.gz
