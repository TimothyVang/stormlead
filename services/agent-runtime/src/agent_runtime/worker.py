"""agent-runtime hatchet worker entrypoint.

registers workflows:
  qualify_lead            triggered by hatchet event "lead.enriched"
  nurture_lead            triggered by hatchet events "lead.unsold"/"lead.rejected"
  hermes_self_evolution   weekly cron (mon 09:00 utc)

model calls are routed through LiteLLM by agent_runtime.execution.
"""

from __future__ import annotations

import asyncio

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger

from agent_runtime.hermes import hermes_self_evolution
from agent_runtime.nurture import nurture_lead
from agent_runtime.qualify import qualify_lead

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)


@hatchet.workflow(name="qualify-lead", on_events=["lead.enriched"])
class QualifyLead:
    @hatchet.step(timeout="120s", retries=2)
    async def step(self, context: Context) -> dict:
        return await qualify_lead(context)


@hatchet.workflow(name="nurture-lead", on_events=["lead.unsold", "lead.rejected"])
class NurtureLead:
    @hatchet.step(timeout="60s", retries=2)
    async def step(self, context: Context) -> dict:
        return await nurture_lead(context)


@hatchet.workflow(name="hermes-self-evolution", on_crons=["0 9 * * 1"])  # mondays 09:00 utc
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
