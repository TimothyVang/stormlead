"""agent-runtime hatchet worker entrypoint.

registers workflows:
  qualify_lead            triggered by hatchet event "lead.enriched"
  nurture_lead            triggered by hatchet events "lead.unsold"/"lead.rejected"
  hermes_self_evolution   weekly cron (mon 09:00 utc)

model calls are routed through LiteLLM by agent_runtime.execution.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger

from agent_runtime.hermes import hermes_self_evolution
from agent_runtime.nurture import nurture_lead
from agent_runtime.qualify import qualify_lead

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")
_legacy_hatchet = cast(Any, hatchet)


class _ContextAdapter:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.workflow_input = payload


def _payload(task_input: Any, context: Context) -> dict[str, Any]:
    if isinstance(task_input, dict):
        return task_input
    model_dump = getattr(task_input, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict) and dumped:
            return dumped
    workflow_input = getattr(context, "workflow_input", None)
    payload = workflow_input() if callable(workflow_input) else workflow_input
    return payload if isinstance(payload, dict) else {}


if _supports_legacy_hatchet_worker:

    @_legacy_hatchet.workflow(name="qualify-lead", on_events=["lead.enriched"])
    class QualifyLead:
        @_legacy_hatchet.step(timeout="120s", retries=2)
        async def step(self, context: Context) -> dict:
            return await qualify_lead(context)

    @_legacy_hatchet.workflow(name="nurture-lead", on_events=["lead.unsold", "lead.rejected"])
    class NurtureLead:
        @_legacy_hatchet.step(timeout="60s", retries=2)
        async def step(self, context: Context) -> dict:
            return await nurture_lead(context)

    @_legacy_hatchet.workflow(name="hermes-self-evolution", on_crons=["0 9 * * 1"])
    class HermesSelfEvolution:
        @_legacy_hatchet.step(timeout="600s", retries=1)
        async def step(self, context: Context) -> dict:
            return await hermes_self_evolution(context)

else:

    @hatchet.task(
        name="qualify-lead",
        on_events=["lead.enriched"],
        execution_timeout="120s",
        retries=2,
    )
    async def qualify_lead_task(task_input: Any, context: Context) -> dict:
        adapted = _ContextAdapter(_payload(task_input, context))
        return await qualify_lead(cast(Context, adapted))

    @hatchet.task(
        name="nurture-lead",
        on_events=["lead.unsold", "lead.rejected"],
        execution_timeout="60s",
        retries=2,
    )
    async def nurture_lead_task(task_input: Any, context: Context) -> dict:
        adapted = _ContextAdapter(_payload(task_input, context))
        return await nurture_lead(cast(Context, adapted))

    @hatchet.task(
        name="hermes-self-evolution",
        on_crons=["0 9 * * 1"],
        execution_timeout="600s",
        retries=1,
    )
    async def hermes_self_evolution_task(task_input: Any, context: Context) -> dict:
        adapted = _ContextAdapter(_payload(task_input, context))
        return await hermes_self_evolution(cast(Context, adapted))


def main() -> None:
    if _supports_legacy_hatchet_worker:
        worker = _legacy_hatchet.worker("agent-runtime", max_runs=4)
        worker.register_workflow(QualifyLead())
        worker.register_workflow(NurtureLead())
        worker.register_workflow(HermesSelfEvolution())
    else:
        worker = hatchet.worker(
            "agent-runtime",
            slots=4,
            workflows=[qualify_lead_task, nurture_lead_task, hermes_self_evolution_task],
        )
    async_start = getattr(worker, "async_start", None)
    if callable(async_start):
        asyncio.run(async_start())
    else:
        worker.start()


if __name__ == "__main__":
    main()
