#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8002}"
PING_POST_URL="${PING_POST_URL:-http://localhost:8003}" 
BUYER_URL="${BUYER_URL:-http://localhost:9999/buyer}"
SKIP_ENRICH="${SKIP_ENRICH:-false}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

printf '==> submitting ingest webhook\n'
cat >"$TMP_DIR/form.json" <<JSON
{
  "lead_id": "smoke-$(date +%s)",
  "zip": "77002",
  "state": "TX",
  "homeowner": true,
  "consent": true,
  "phone": "+15555550123"
}
JSON

curl -fsS -X POST "$BASE_URL/webhooks/formbricks" \
  -H 'content-type: application/json' \
  -d @"$TMP_DIR/form.json" >/dev/null

printf '==> verifying qualify->auction health\n'
curl -fsS "$PING_POST_URL/health" >/dev/null

if [[ "$SKIP_ENRICH" == "true" ]]; then
  printf '==> enrichment skipped (SKIP_ENRICH=true)\n'
fi

printf '==> probing buyer endpoint contract\n'
curl -fsS -X POST "$BUYER_URL" \
  -H 'content-type: application/json' \
  -d '{"probe": "stormlead-smoke"}' >/dev/null || {
    echo "buyer endpoint probe failed"
    exit 1
  }

printf 'smoke path ingest->qualify->auction checks passed\n'
