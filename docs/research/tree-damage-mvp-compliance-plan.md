# Tree Damage MVP Compliance Plan

This repo targets local/synthetic proof until explicit commercial launch approval.

## Ad Acquisition

- Use standard mobile Google Search campaigns and call assets for the MVP.
- Do not use Google Local Services Ads as a lead resale source.
- Do not depend on Google lead-form assets unless policy/legal review approves the exact aggregator flow.
- Preserve UTM/click attribution for offline conversion import readiness.

## Intake And Consent

- Landing intake captures contact details, address, GPS/photo evidence, damage type, urgency, power-line status, injury status, active-danger status, and exact consent text.
- Consent copy must disclose AI-assisted review, provider sharing, optional consent, and STOP opt-out.
- Privacy and terms copy must disclose GPS/photo handling and emergency limitations.

## Safety Gate

- Power lines, injuries, active danger, roof impact, and tree-on-structure flags require human review.
- Safety-gated leads must not enter automatic buyer auction or delivery.
- User-facing copy tells homeowners to avoid hazards and contact emergency services or utilities for immediate danger.

## Buyer Delivery

- Pre-sale ping payload stays PII-free.
- Full lead delivery remains local-only unless commercial launch approval, buyer verification gates, and an approved HTTPS buyer webhook host are configured.
- Nurture outreach remains disabled or local-only unless commercial launch approval and an approved HTTPS nurture webhook host are configured.
- Restricted resale sources such as Google LSA are blocked from auction.
