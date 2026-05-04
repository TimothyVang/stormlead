"""agent-runtime hatchet worker entrypoint.

registers two workflows:
  qualify_lead            triggered by hatchet event "lead.captured"
  hermes_self_evolution   weekly cron (mon 09:00 utc)

both use opus via oauth (CLAUDE_CODE_OAUTH_TOKEN). see auth.py for
the backend-selection logic.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger, suppresses_outbound
from stormlead_db import LeadRow, get_session
from stormlead_db.compliance import record_compliance_decision_log

from agent_runtime.hermes import hermes_self_evolution
from agent_runtime.qualify import qualify_lead

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)


async def enforce_outbound_compliance_or_block(*, lead_id: UUID, action: str, actor: str) -> bool:
    """Shared guard for nurture/voice outbound channels."""
    async with get_session() as s:
        lead = await s.get(LeadRow, lead_id)
    if lead is None:
        raise ValueError(f"lead {lead_id} not found")

    gate = await suppresses_outbound(lead.phone_e164, lead.email)
    if gate.blocked:
        await record_compliance_decision_log(
            actor=actor,
            action=action,
            lead_id=lead_id,
            buyer_id=None,
            blocked=True,
            rule_hit=gate.rule_hit,
            details={"source": gate.source, "phone_e164": lead.phone_e164},
        )
        log.info("outbound.blocked", lead_id=str(lead_id), action=action, rule=gate.rule_hit)
        return False

    await record_compliance_decision_log(
        actor=actor,
        action=action,
        lead_id=lead_id,
        buyer_id=None,
        blocked=False,
        rule_hit=None,
        details={"source": None},
    )
    return True


@hatchet.workflow(on_events=["lead.captured"])
class QualifyLead:
    @hatchet.step(timeout="120s", retries=2)
    async def step(self, context: Context) -> dict:
        return await qualify_lead(context)


@hatchet.workflow(on_events=["lead.nurture.requested"])
class NurtureLead:
    @hatchet.step(timeout="120s", retries=2)
    async def step(self, context: Context) -> dict:
        payload = context.workflow_input()
        lead_id = UUID(payload["lead_id"])
        allowed = await enforce_outbound_compliance_or_block(
            lead_id=lead_id,
            action="nurture_outbound",
            actor="agent-runtime.worker",
        )
        return {"lead_id": str(lead_id), "allowed": allowed}


@hatchet.workflow(on_crons=["0 9 * * 1"])  # mondays 09:00 utc
class HermesSelfEvolution:
    @hatchet.step(timeout="600s", retries=1)
    async def step(self, context: Context) -> dict:
        return await hermes_self_evolution(context)


def main() -> None:
    worker = hatchet.worker("agent-runtime", max_runs=4)
    worker.register_workflow(QualifyLead())
    worker.register_workflow(NurtureLead())
    worker.register_workflow(HermesSelfEvolution())
    asyncio.run(worker.async_start())


if __name__ == "__main__":
    main()
