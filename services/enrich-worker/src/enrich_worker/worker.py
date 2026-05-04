from __future__ import annotations

import asyncio
from typing import Any, cast

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger

from enrich_worker.enrich import enrich_lead

configure_logging()
log = get_logger(__name__)
hatchet = Hatchet(debug=False)
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")


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

    @hatchet.workflow(name="enrich-lead", on_events=["lead.captured"])
    class EnrichLead:
        @hatchet.step(timeout="60s", retries=2)
        async def step(self, context: Context) -> dict:
            return await enrich_lead(context)

else:

    @hatchet.task(
        name="enrich-lead",
        on_events=["lead.captured"],
        execution_timeout="60s",
        retries=2,
    )
    async def enrich_lead_task(task_input: Any, context: Context) -> dict:
        adapted = _ContextAdapter(_payload(task_input, context))
        return await enrich_lead(cast(Context, adapted))


def main() -> None:
    if _supports_legacy_hatchet_worker:
        worker = hatchet.worker("enrich-worker", max_runs=4)
        worker.register_workflow(EnrichLead())
    else:
        worker = hatchet.worker("enrich-worker", slots=4, workflows=[enrich_lead_task])
    async_start = getattr(worker, "async_start", None)
    if callable(async_start):
        asyncio.run(async_start())
    else:
        worker.start()


if __name__ == "__main__":
    main()
