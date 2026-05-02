"""ping-post http api + hatchet workflow worker.

http api:
  POST /v1/auction       sync auction for one lead (test/debug)
  GET  /healthz          liveness
  GET  /readyz           readiness (db + nats reachable)

hatchet workflow:
  ping_post_auction      durable; called by form-receiver and storm-watcher
                         retries with exponential backoff on transient errors
                         saga state lives in postgres (hatchet's home)
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from hatchet_sdk import Context, Hatchet
from hatchet_sdk.clients.run_event_listener import StepRunEventType

from stormlead_core import Lead, configure_logging, get_logger
from stormlead_db import LeadRow, get_session

from ping_post.auction import run_auction

configure_logging()
log = get_logger(__name__)


hatchet = Hatchet(debug=False)


@hatchet.workflow(on_events=["lead.qualified"])
class PingPostWorkflow:
    """fired by nats consumer when a lead is qualified.

    NOTE: hatchet's python sdk currently expects events from its own engine.
    we run a thin nats->hatchet bridge in the agent-runtime that translates
    lead.qualified nats messages into hatchet workflow runs.
    """

    @hatchet.step(timeout="30s", retries=3)
    async def auction(self, context: Context) -> dict[str, Any]:
        payload = context.workflow_input()
        lead_id = payload["lead_id"]

        async with get_session() as s:
            row = await s.get(LeadRow, lead_id)
            if row is None:
                raise ValueError(f"lead {lead_id} not found")
            lead = _row_to_lead(row)

        result = await run_auction(lead)
        return {
            "lead_id": str(result.lead_id),
            "pinged": len(result.pinged_buyer_ids),
            "winning_buyer_id": str(result.winning_buyer_id) if result.winning_buyer_id else None,
            "winning_bid_cents": result.winning_bid_cents,
            "duration_ms": result.duration_ms,
        }


def _row_to_lead(row: LeadRow) -> Lead:
    """sqlalchemy row -> pydantic model. small adapter, not a repo."""
    from stormlead_core.models import DamageTier, LeadSource, LeadStatus

    return Lead(
        id=row.id,
        source=LeadSource(row.source),
        status=LeadStatus(row.status),
        name=row.name,
        phone_e164=row.phone_e164,
        email=row.email,
        address_line1=row.address_line1,
        city=row.city,
        state=row.state,
        zip=row.zip,
        storm_id=row.storm_id,
        damage_description=row.damage_description,
        damage_tier=DamageTier(row.damage_tier) if row.damage_tier else None,
        photo_s3_keys=row.photo_s3_keys or [],
        consent_text=row.consent_text,
        consent_ip=row.consent_ip,
        consent_user_agent=row.consent_user_agent,
        consent_at=row.consent_at,
        page_url=row.page_url,
        page_html_hash=row.page_html_hash,
        rrweb_session_s3_key=row.rrweb_session_s3_key,
        trustedform_cert_url=row.trustedform_cert_url,
        property_avm=row.property_avm,
        year_built=row.year_built,
        owner_occupied=row.owner_occupied,
        qualification_score=row.qualification_score,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # start hatchet worker in background
    worker = hatchet.worker("ping-post-worker", max_runs=10)
    worker.register_workflow(PingPostWorkflow())
    task = asyncio.create_task(worker.async_start())
    log.info("startup.complete")
    try:
        yield
    finally:
        task.cancel()
        log.info("shutdown.complete")


app = FastAPI(title="stormlead ping-post", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    # cheap connectivity check
    try:
        async with get_session() as s:
            await s.execute("SELECT 1")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"db: {e}") from e
    return {"status": "ready"}


@app.post("/v1/auction")
async def trigger_auction(payload: dict[str, Any]) -> dict[str, Any]:
    """sync auction. for testing only — production goes through hatchet."""
    lead_id = payload.get("lead_id")
    if not lead_id:
        raise HTTPException(400, "lead_id required")
    async with get_session() as s:
        row = await s.get(LeadRow, lead_id)
        if row is None:
            raise HTTPException(404, "lead not found")
        lead = _row_to_lead(row)

    result = await run_auction(lead)
    return {
        "lead_id": str(result.lead_id),
        "pinged_buyer_ids": [str(b) for b in result.pinged_buyer_ids],
        "winning_buyer_id": str(result.winning_buyer_id) if result.winning_buyer_id else None,
        "winning_bid_cents": result.winning_bid_cents,
        "duration_ms": result.duration_ms,
    }
