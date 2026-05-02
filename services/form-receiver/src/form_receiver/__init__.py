"""form-receiver: ingest formbricks webhooks; capture tcpa consent; emit lead.captured.

contract:
  POST /webhooks/formbricks  standard-webhooks signature verification +
                              constant-time compare + ±5-min replay window.
                              dedupes on the `webhook-id` header (a primary
                              key on consent_audits). emits a hatchet
                              `lead.captured` event after a successful new
                              row write so agent-runtime's QualifyLead
                              workflow picks it up.

phase 1 audit fields (TSR floor + tamper-evidence): timestamp, ip, user_agent,
page_url, consent_text, phone, email, name, page_html_sha256, dwell_ms,
plus webhook_id and the raw payload (jsonb).

phase 2 (deferred — flagged for a future commit, not built here):
  - rrweb session capture → s3 (compressed, content-addressed)
  - playwright server-side page snapshots at form-load + submit → s3 with object-lock
  - trustedform / jornaya cert capture
  - 7-yr retention policy enforcement at the bucket level

see docs/research/2026-05-stack-improvements.md for the broader compliance
sequence and docs/research/2026-05-architectural-fit.md for the v1 scope.
"""
