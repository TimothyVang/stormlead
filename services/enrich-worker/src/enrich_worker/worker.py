from __future__ import annotations

import asyncio

from hatchet_sdk import Context, Hatchet
from stormlead_core import configure_logging, get_logger

from enrich_worker.enrich import enrich_lead

configure_logging()
log = get_logger(__name__)
hatchet = Hatchet(debug=False)


@hatchet.workflow(name="enrich-lead", on_events=["lead.captured"])
class EnrichLead:
    @hatchet.step(timeout="60s", retries=2)
    async def step(self, context: Context) -> dict:
        return await enrich_lead(context)


def main() -> None:
    worker = hatchet.worker("enrich-worker", max_runs=4)
    worker.register_workflow(EnrichLead())
    asyncio.run(worker.async_start())


if __name__ == "__main__":
    main()
