#!/bin/bash
set -euo pipefail

ROOT_DIR="${STORMLEAD_DEPLOY_DIR:-/opt/stormlead}"
ENV_FILE="${STORMLEAD_ENV_FILE:-${ROOT_DIR}/.env.prod}"
COMPOSE_FILE="${STORMLEAD_COMPOSE_FILE:-infra/compose/prod/docker-compose.yml}"

cd "${ROOT_DIR}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" pull
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans

curl -fsS --retry 30 --retry-delay 2 http://127.0.0.1/healthz >/dev/null
curl -fsS --retry 30 --retry-delay 2 http://127.0.0.1/ping-post/healthz >/dev/null

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
