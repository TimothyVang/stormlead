"""form-receiver fastapi app.

POST /webhooks/formbricks  standard-webhooks sig verify + consent extract +
                           lead persist + audit row + lead.captured event
GET  /healthz              liveness
GET  /readyz               readiness (db reachable)

response codes:
  200  accepted (new) or accepted-duplicate (idempotent retry)
  400  missing headers / malformed body / failed consent extraction
  401  signature mismatch
  409  replay outside ±5-min window
  5xx  transient db / hatchet failure → formbricks will retry
       (deliberately *not* 410, which would permanently disable the webhook)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from hatchet_sdk import Hatchet
from sqlalchemy import text as sa_text
from stormlead_core import configure_logging, get_logger
from stormlead_db import get_session

from form_receiver.schemas import (
    ConsentExtractionError,
    FormbricksEnvelope,
    extract_consent,
)
from form_receiver.signatures import (
    InvalidSignatureError,
    MissingHeaderError,
    NoopDncChecker,
    ReplayError,
    verify,
)
from form_receiver.storage import emit_lead_captured, record_audit, upsert_lead

configure_logging()
log = get_logger(__name__)


_hatchet: Hatchet | None = None
_dnc_checker = NoopDncChecker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _hatchet
    _hatchet = Hatchet(debug=False)
    log.info("startup.complete")
    try:
        yield
    finally:
        log.info("shutdown.complete")


app = FastAPI(title="stormlead form-receiver", lifespan=lifespan)


def _client_ip(request: Request) -> str:
    """trust the first X-Forwarded-For hop when behind a reverse proxy.

    in prod, caddy strips/sets this header. for dev, falls back to the
    immediate peer.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    try:
        async with get_session() as s:
            await s.execute(sa_text("SELECT 1"))
    except Exception as e:
        raise HTTPException(503, f"db: {e}") from e
    return {"status": "ready"}


@app.post("/webhooks/formbricks")
async def formbricks_webhook(request: Request) -> dict[str, str]:
    raw_body = await request.body()
    secret = os.environ.get("FORMBRICKS_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(500, "FORMBRICKS_WEBHOOK_SECRET not configured")

    # 1. signature
    try:
        verify(
            raw_body=raw_body,
            webhook_id=request.headers.get("webhook-id"),
            webhook_timestamp=request.headers.get("webhook-timestamp"),
            webhook_signature=request.headers.get("webhook-signature"),
            secret=secret,
        )
    except MissingHeaderError as e:
        raise HTTPException(400, str(e)) from e
    except ReplayError as e:
        raise HTTPException(409, str(e)) from e
    except InvalidSignatureError as e:
        raise HTTPException(401, str(e)) from e

    # 2. parse + filter
    try:
        envelope = FormbricksEnvelope.model_validate_json(raw_body)
    except Exception as e:
        raise HTTPException(400, f"malformed envelope: {e}") from e

    if envelope.event != "responseFinished":
        # only finished responses are persisted; partials are noise
        log.info("webhook.skipped_event", event=envelope.event, webhook_id=envelope.webhookId)
        return {"status": "skipped", "reason": f"event {envelope.event} not persisted"}

    # 3. extract consent
    try:
        extracted = extract_consent(envelope)
    except ConsentExtractionError as e:
        raise HTTPException(400, str(e)) from e

    ip = _client_ip(request)
    webhook_id = request.headers["webhook-id"]

    dnc_result = await _dnc_checker.check(extracted.phone_e164)
    if not dnc_result.allowed:
        extracted = extracted.model_copy(update={"voice_outreach_permitted": False})
        log.info("webhook.outreach_blocked", lead_phone=extracted.phone_e164, reason=dnc_result.reason, source=dnc_result.source)

    # 4. persist + emit
    lead_id = await upsert_lead(extracted, ip=ip)
    was_new = await record_audit(
        webhook_id=webhook_id,
        lead_id=lead_id,
        extracted=extracted,
        ip=ip,
        raw_payload=raw_body,
    )
    if was_new:
        try:
            if _hatchet is None:
                raise RuntimeError("hatchet client not initialized")
            await emit_lead_captured(_hatchet, lead_id)
        except Exception as e:
            # raise 5xx so formbricks retries — webhook_id dedup means
            # the lead/audit rows aren't double-written on retry.
            log.error("event.push_failed", error=str(e), lead_id=str(lead_id))
            raise HTTPException(503, "event emission failed; will retry") from e
        return {"status": "accepted", "lead_id": str(lead_id)}

    log.info("webhook.duplicate", webhook_id=webhook_id, lead_id=str(lead_id))
    return {"status": "accepted-duplicate", "lead_id": str(lead_id)}
