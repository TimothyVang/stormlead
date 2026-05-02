"""storm-watcher main entry. registers hatchet cron workflows.

cron schedule (utc):
  nws cap            every 5 min
  fema declarations  every 30 min
  nhc atcf (tropycal) every 15 min during hurricane season (jun-nov)

each tick: fetch -> dedupe by external_id -> upsert -> emit nats.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from hatchet_sdk import Context, Hatchet
from nats.aio.client import Client as NATSClient
from sqlalchemy.dialects.postgresql import insert as pg_insert

from stormlead_core import StormDetected, configure_logging, get_logger
from stormlead_db import StormRow, get_session

from storm_watcher.fema import fetch_recent_declarations, normalize_declaration
from storm_watcher.nws import fetch_active_alerts, normalize_alert

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)


async def _publish_storm_detected(storm) -> None:  # type: ignore[no-untyped-def]
    nc = NATSClient()
    await nc.connect(os.environ["NATS_URL"])
    try:
        evt = StormDetected(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            storm=storm,
        )
        await nc.publish(
            f"storms.detected.{storm.source}",
            json.dumps(evt.model_dump(mode="json")).encode(),
        )
    finally:
        await nc.close()


async def _upsert_storm(storm) -> bool:  # type: ignore[no-untyped-def]
    """returns True if this is a new storm (vs already-seen update)."""
    async with get_session() as s:
        stmt = (
            pg_insert(StormRow)
            .values(
                id=storm.id,
                external_id=storm.external_id,
                name=storm.name[:128],
                source=storm.source,
                severity=storm.severity.value,
                affected_states=storm.affected_states,
                affected_counties=storm.affected_counties,
                detected_at=storm.detected_at,
                declared_at=storm.declared_at,
                raw=storm.raw,
            )
            .on_conflict_do_update(
                index_elements=["external_id"],
                set_={"severity": storm.severity.value, "raw": storm.raw},
            )
            .returning(StormRow.id, StormRow.created_at)
        )
        result = (await s.execute(stmt)).first()
        if result is None:
            return False
        # heuristic: created_at is "now" => new row
        return (datetime.now(timezone.utc) - result.created_at).total_seconds() < 5


@hatchet.workflow(on_crons=["*/5 * * * *"])
class NwsCapPoller:
    @hatchet.step(timeout="60s", retries=2)
    async def poll(self, context: Context) -> dict:
        try:
            features = await fetch_active_alerts()
        except Exception as e:  # noqa: BLE001
            log.error("nws.fetch_failed", error=str(e))
            return {"error": str(e), "found": 0}

        new_count = 0
        for f in features:
            storm = normalize_alert(f)
            if storm is None:
                continue
            try:
                if await _upsert_storm(storm):
                    new_count += 1
                    await _publish_storm_detected(storm)
            except Exception as e:  # noqa: BLE001
                log.error("nws.upsert_failed", external_id=storm.external_id, error=str(e))

        log.info("nws.poll_done", total=len(features), new=new_count)
        return {"total": len(features), "new": new_count}


@hatchet.workflow(on_crons=["*/30 * * * *"])
class FemaPoller:
    @hatchet.step(timeout="120s", retries=2)
    async def poll(self, context: Context) -> dict:
        try:
            declarations = await fetch_recent_declarations(days_back=14)
        except Exception as e:  # noqa: BLE001
            log.error("fema.fetch_failed", error=str(e))
            return {"error": str(e), "found": 0}

        new_count = 0
        for d in declarations:
            storm = normalize_declaration(d)
            try:
                if await _upsert_storm(storm):
                    new_count += 1
                    await _publish_storm_detected(storm)
            except Exception as e:  # noqa: BLE001
                log.error("fema.upsert_failed", external_id=storm.external_id, error=str(e))

        log.info("fema.poll_done", total=len(declarations), new=new_count)
        return {"total": len(declarations), "new": new_count}


def main() -> None:
    worker = hatchet.worker("storm-watcher", max_runs=5)
    worker.register_workflow(NwsCapPoller())
    worker.register_workflow(FemaPoller())
    asyncio.run(worker.async_start())


if __name__ == "__main__":
    main()
