"""agent-runtime hatchet worker entrypoint.

registers two workflows:
  qualify_lead            triggered by hatchet event "lead.captured"
  hermes_self_evolution   weekly cron (mon 09:00 utc)

both use opus via oauth (CLAUDE_CODE_OAUTH_TOKEN). see auth.py for
the backend-selection logic.
"""

from __future__ import annotations

import asyncio

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger

from agent_runtime.hermes import hermes_self_evolution
from agent_runtime.qualify import qualify_lead

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)


@hatchet.workflow(name="qualify-lead", on_events=["lead.captured"])
class QualifyLead:
    @hatchet.step(timeout="120s", retries=2)
    async def step(self, context: Context) -> dict:
        return await qualify_lead(context)


@hatchet.workflow(name="hermes-self-evolution", on_crons=["0 9 * * 1"])  # mondays 09:00 utc
class HermesSelfEvolution:
    @hatchet.step(timeout="600s", retries=1)
    async def step(self, context: Context) -> dict:
        return await hermes_self_evolution(context)


def main() -> None:
    worker = hatchet.worker("agent-runtime", max_runs=4)
    worker.register_workflow(QualifyLead())
    worker.register_workflow(HermesSelfEvolution())
    asyncio.run(worker.async_start())


if __name__ == "__main__":
    main()
