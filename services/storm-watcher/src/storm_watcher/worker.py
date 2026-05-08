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
from typing import Any

from hatchet_sdk import Context, Hatchet
from sqlalchemy.dialects.postgresql import insert as pg_insert
from stormlead_core import ERROR_SINK, configure_logging, emit_metric, get_logger
from stormlead_db import StormRow, get_session

from storm_watcher.fema import fetch_recent_declarations, normalize_declaration
from storm_watcher.nws import fetch_active_alerts, normalize_alert
from storm_watcher.tropycal_poller import fetch_active_tropical_systems, normalize_tropical_storm

configure_logging()
log = get_logger(__name__)

hatchet = Hatchet(debug=False)
_supports_legacy_hatchet_worker = hasattr(hatchet, "step")


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


async def _poll_nws() -> dict[str, Any]:
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


async def _poll_fema() -> dict[str, Any]:
    try:
        declarations = await fetch_recent_declarations(days_back=14)
    except Exception as e:
        ERROR_SINK.report("storm-watcher", "fema_fetch", e)
        log.error("fema.fetch_failed", error=str(e))
        return {"error": str(e), "found": 0}

    new_count = 0
    for d in declarations:
        storm = normalize_declaration(d)
        if storm is None:
            continue
        try:
            if await _upsert_storm(storm):
                new_count += 1
        except Exception as e:
            ERROR_SINK.report("storm-watcher", "fema_upsert", e, external_id=storm.external_id)
            log.error("fema.upsert_failed", external_id=storm.external_id, error=str(e))

    log.info("fema.poll_done", total=len(declarations), new=new_count)
    return {"total": len(declarations), "new": new_count}


def _is_hurricane_season(now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    return 6 <= current.month <= 11


async def _poll_nhc_tropycal() -> dict[str, Any]:
    if not _is_hurricane_season():
        return {"skipped": True, "reason": "outside_hurricane_season"}

    try:
        systems = await fetch_active_tropical_systems()
    except Exception as e:
        ERROR_SINK.report("storm-watcher", "nhc_tropycal_fetch", e)
        log.error("nhc_tropycal.fetch_failed", error=str(e))
        return {"error": str(e), "found": 0}

    new_count = 0
    for system in systems:
        storm = normalize_tropical_storm(system)
        if storm is None:
            continue
        try:
            if await _upsert_storm(storm):
                new_count += 1
        except Exception as e:
            ERROR_SINK.report(
                "storm-watcher", "nhc_tropycal_upsert", e, external_id=storm.external_id
            )
            log.error("nhc_tropycal.upsert_failed", external_id=storm.external_id, error=str(e))

    log.info("nhc_tropycal.poll_done", total=len(systems), new=new_count)
    return {"total": len(systems), "new": new_count}


if _supports_legacy_hatchet_worker:

    @hatchet.workflow(name="nws-cap-poller", on_crons=["*/5 * * * *"])
    class NwsCapPoller:
        @hatchet.step(timeout="60s", retries=2)
        async def poll(self, context: Context) -> dict:
            return await _poll_nws()

    @hatchet.workflow(name="fema-poller", on_crons=["*/30 * * * *"])
    class FemaPoller:
        @hatchet.step(timeout="120s", retries=2)
        async def poll(self, context: Context) -> dict:
            return await _poll_fema()

    @hatchet.workflow(name="NHCTropycalPoller", on_crons=["*/15 * * * *"])
    class NHCTropycalPoller:
        @hatchet.step(timeout="180s", retries=2)
        async def poll(self, context: Context) -> dict:
            return await _poll_nhc_tropycal()

else:

    @hatchet.task(
        name="nws-cap-poller",
        on_crons=["*/5 * * * *"],
        execution_timeout="60s",
        retries=2,
    )
    async def nws_cap_poller_task(task_input: Any, context: Context) -> dict[str, Any]:
        return await _poll_nws()

    @hatchet.task(
        name="fema-poller",
        on_crons=["*/30 * * * *"],
        execution_timeout="120s",
        retries=2,
    )
    async def fema_poller_task(task_input: Any, context: Context) -> dict[str, Any]:
        return await _poll_fema()

    @hatchet.task(
        name="NHCTropycalPoller",
        on_crons=["*/15 * * * *"],
        execution_timeout="180s",
        retries=2,
    )
    async def nhc_tropycal_poller_task(task_input: Any, context: Context) -> dict[str, Any]:
        return await _poll_nhc_tropycal()


def main() -> None:
    if _supports_legacy_hatchet_worker:
        worker = hatchet.worker("storm-watcher", max_runs=5)
        worker.register_workflow(NwsCapPoller())
        worker.register_workflow(FemaPoller())
        worker.register_workflow(NHCTropycalPoller())
    else:
        worker = hatchet.worker(
            "storm-watcher",
            slots=5,
            workflows=[nws_cap_poller_task, fema_poller_task, nhc_tropycal_poller_task],
        )
    async_start = getattr(worker, "async_start", None)
    if callable(async_start):
        asyncio.run(async_start())
    else:
        worker.start()


if __name__ == "__main__":
    main()
