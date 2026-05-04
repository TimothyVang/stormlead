"""storm-watcher main entry. registers hatchet cron workflows.

cron schedule (utc):
  nws cap            every 5 min
  fema declarations  every 30 min
  nhc atcf (tropycal) every 15 min during hurricane season (jun-nov)

each tick: fetch -> dedupe by external_id -> upsert. downstream consumers
read via postgres listen/notify or a hatchet event trigger fan-out (when
agent-runtime lands). nats was removed in commit cfb2c15 — see
docs/research/2026-05-architectural-fit.md.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from hatchet_sdk import Context, Hatchet
from sqlalchemy.dialects.postgresql import insert as pg_insert
from stormlead_core import ERROR_SINK, configure_logging, emit_metric, get_logger
from stormlead_db import StormRow, get_session

from storm_watcher.fema import fetch_recent_declarations, normalize_declaration
from storm_watcher.nws import fetch_active_alerts, normalize_alert

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)


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
        return (datetime.now(UTC) - result.created_at).total_seconds() < 5


@hatchet.workflow(on_crons=["*/5 * * * *"])
class NwsCapPoller:
    @hatchet.step(timeout="60s", retries=2)
    async def poll(self, context: Context) -> dict:
        try:
            features = await fetch_active_alerts()
        except Exception as e:
            ERROR_SINK.report("storm-watcher", "nws_fetch", e)
            emit_metric("buyer_endpoint_failures", service="storm-watcher", source="nws")
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
            except Exception as e:
                ERROR_SINK.report("storm-watcher", "nws_upsert", e, external_id=storm.external_id)
                log.error("nws.upsert_failed", external_id=storm.external_id, error=str(e))

        log.info("nws.poll_done", total=len(features), new=new_count)
        return {"total": len(features), "new": new_count}


@hatchet.workflow(on_crons=["*/30 * * * *"])
class FemaPoller:
    @hatchet.step(timeout="120s", retries=2)
    async def poll(self, context: Context) -> dict:
        try:
            declarations = await fetch_recent_declarations(days_back=14)
        except Exception as e:
            ERROR_SINK.report("storm-watcher", "fema_fetch", e)
            log.error("fema.fetch_failed", error=str(e))
            return {"error": str(e), "found": 0}

        new_count = 0
        for d in declarations:
            storm = normalize_declaration(d)
            try:
                if await _upsert_storm(storm):
                    new_count += 1
            except Exception as e:
                ERROR_SINK.report("storm-watcher", "fema_upsert", e, external_id=storm.external_id)
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
