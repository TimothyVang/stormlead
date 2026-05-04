from __future__ import annotations

from dataclasses import dataclass

from stormlead_db.compliance import lookup_dnc, lookup_suppression


@dataclass(frozen=True)
class ComplianceGate:
    blocked: bool
    rule_hit: str | None = None
    source: str | None = None


async def suppresses_outbound(phone_e164: str, email: str | None = None) -> ComplianceGate:
    suppression = await lookup_suppression(phone_e164, email)
    if suppression.blocked:
        return ComplianceGate(True, suppression.rule, suppression.source)
    dnc = await lookup_dnc(phone_e164)
    if dnc.blocked:
        return ComplianceGate(True, dnc.rule, dnc.source)
    return ComplianceGate(False)
