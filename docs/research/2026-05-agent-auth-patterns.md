# 2026-05 agent auth patterns

Dated agent-auth research. This version is sanitized to keep review-only wording out of source docs.

## current runtime decision

Runtime services use LiteLLM only.

- `agent-runtime` calls the LiteLLM OpenAI-compatible endpoint.
- Static tests reject direct provider SDK imports in runtime source.
- Model route selection belongs in LiteLLM config, not scattered service code.

## historical context

Earlier research evaluated whether personal CLI auth could support single-operator agent work. The current milestone no longer depends on that path.

## operational shape

- High-volume qualification and nurture paths should use LiteLLM routes.
- Complex operator-only research can use local CLI tooling outside runtime services.
- Buyer-facing product paths should not depend on local operator auth state.
- If a model path affects lead lifecycle, persist model route, latency, cost estimate, score/class, and deterministic gate outcome.

## fallback

If any provider route fails, fall back through LiteLLM config rather than changing application code.
