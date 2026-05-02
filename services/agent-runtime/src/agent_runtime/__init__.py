"""agent-runtime: claude-agent-sdk workers for stormlead.

two hatchet workflows registered:
  qualify_lead            event-triggered (lead.captured); opus via oauth
  hermes_self_evolution   weekly cron (mon 09:00 utc); opus via oauth

auth: hybrid per docs/research/2026-05-agent-auth-patterns.md.
  - hermes + complex qualification → CLAUDE_CODE_OAUTH_TOKEN (opus, flat-rate)
  - any future bulk path           → litellm proxy (haiku, pay-per-token)
"""
