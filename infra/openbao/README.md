# openbao — deferred

openbao re-enters when there are 2+ operators with overlapping access. until then, v1 uses sops-encrypted `.env.prod` with an age key (stored in 1password / yubikey).

rationale: `docs/research/2026-05-architectural-fit.md` (decision: tier-1 cuts).
