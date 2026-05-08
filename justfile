# stormlead justfile
# install just: cargo install just OR brew install just OR apt install just
# run: just <target>

set dotenv-load

# default target: show help
default:
    @just --list

# --- dev stack ---

# bring up the lean wsl2 dev stack: local APIs + required workflow infra only
up:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml up -d
    @echo "lean stack up. landing: http://localhost:8005  buyer: http://localhost:8004  form: http://localhost:8002  ping-post: http://localhost:8003"
    @echo "need workflow workers? run: just up-pipeline. need every optional service? run: just up-full"

# bring up the synthetic workflow stack: lean stack + workers + LiteLLM
up-pipeline:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml --profile pipeline up -d
    @echo "pipeline stack up. litellm: http://localhost:4000"

# bring up every dev service, including observability, watcher, MCP, and UIs
up-full:
    docker compose --env-file .env -f infra/compose/dev/docker-compose.yml --profile full up -d
    @echo "full stack up. langfuse: http://localhost:3001  hatchet: http://localhost:8080  litellm: http://localhost:4000"

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

# migrate + seed run on the host (not in a container), so they need
# DATABASE_URL_HOST (localhost:5433) instead of the in-container
# DATABASE_URL (postgres:5432). same trick for both.
#
# init_db.py runs sqlalchemy.create_all first because 0001_initial.py
# expects tables to already exist (it just sets up hypertables); then
# alembic applies every idempotent migration through head.
migrate:
    DATABASE_URL="$DATABASE_URL_HOST" uv run python scripts/init_db.py
    cd libs/stormlead_db && DATABASE_URL="$DATABASE_URL_HOST" uv run alembic upgrade head

migrate-rev MSG:
    cd libs/stormlead_db && DATABASE_URL="$DATABASE_URL_HOST" uv run alembic revision --autogenerate -m "{{MSG}}"

seed:
    DATABASE_URL="$DATABASE_URL_HOST" uv run python scripts/seed_dev.py

# --- tests ---

test:
    uv run pytest -x -q services libs

test-watch:
    uv run pytest-watch -- -x -q services libs

# --- smoke test: real lead → ping-post → buyer → return review → report ---
smoke:
    uv run python scripts/smoke_e2e.py

replay-lead LEAD_ID:
    DATABASE_URL="$DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id "{{LEAD_ID}}"

replay-lead-from LEAD_ID FROM_STATE:
    DATABASE_URL="$DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id "{{LEAD_ID}}" --from-state "{{FROM_STATE}}"

replay-lead-execute LEAD_ID FROM_STATE:
    DATABASE_URL="$DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id "{{LEAD_ID}}" --from-state "{{FROM_STATE}}" --execute

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
