# Senior Research Decision Memo

Topic: How to get StormLead from local synthetic lead ingestion to production-grade autonomous lead generation.

Generated: 2026-05-10

## Provisional Decision

Status: approved with caveats.

The original high-data runner produced a noisy corpus with one unsupported/unfetched candidate and insufficient official-source coverage. That candidate has been excluded from the validated roadmap. A supplemental source-backed roadmap now cites fetched primary/official sources for ad APIs, payments, self-hosting, compliance, and observability.

## Evidence Posture

- Sources selected: 129
- Fetched sources: 128
- Evidence entries: 128
- Citation validation records: 128
- Citation failures: 0 after excluding the unfetched runner candidate from final synthesis
- Official/manual primary-source records added: 21
- Validated output artifact: `validated-roadmap.md`

## Architect Review

Status: approved with caveats. The remaining caveats are non-blocking research/implementation gates: Meta developer docs require manual verification, Microsoft conversion/offline conversion docs require manual review before implementation, and compliance remains counsel-gated rather than legal advice.

## Decision

StormLead can move from local synthetic proof to production only through staged gates. It should not be represented as fully autonomous for real paid lead acquisition until real traffic, public ingestion, production database safety, buyer delivery, payments, opt-out/consent compliance, monitoring, and recovery have passed capped canaries.

## Remaining Uncertainty

- Meta developer docs were inaccessible through webfetch; official SDK repositories were used as partial fallback only.
- Microsoft conversion/offline conversion docs need a successful fetch or manual review before implementing conversion feedback.
- Compliance conclusions require counsel review and are not legal advice.
- Real ad spend, real homeowner contact, real buyer delivery, and live payment capture remain approval-gated.
