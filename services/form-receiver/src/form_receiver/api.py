"""form-receiver fastapi app.

POST /webhooks/formbricks  standard-webhooks sig verify + consent extract +
                           lead persist + audit row + lead.captured event
GET  /healthz              liveness
GET  /readyz               readiness (db reachable)

response codes:
  200  accepted (new) or accepted-duplicate (idempotent retry)
  400  missing headers / malformed body / failed consent extraction
  401  signature mismatch
  409  replay outside ±5-min window or duplicate lead window
  5xx  transient db / hatchet failure → formbricks will retry
       (deliberately *not* 410, which would permanently disable the webhook)
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from hatchet_sdk import Hatchet
from sqlalchemy import text as sa_text
from stormlead_core import (
    ERROR_SINK,
    bind_correlation_id,
    configure_logging,
    emit_event,
    emit_metric,
    get_logger,
)
from stormlead_db import get_session

from form_receiver.call_tracking import (
    CallTrackingEvent,
    ingest_call_event,
    verify_call_tracking_signature,
)
from form_receiver.compliance import verify_trustedform_cert
from form_receiver.schemas import (
    ConsentExtractionError,
    FormbricksEnvelope,
    SuppressionRequest,
    extract_consent,
)
from form_receiver.signatures import (
    InvalidSignatureError,
    MissingHeaderError,
    ReplayError,
    verify,
)
from form_receiver.storage import (
    DuplicateLeadError,
    SuppressedLeadError,
    capture_status_for_webhook,
    claim_capture_event_dispatch,
    emit_lead_captured,
    mark_capture_event_emitted,
    mark_capture_event_failed,
    record_audit,
    record_suppression,
    upsert_lead,
)

configure_logging()
log = get_logger(__name__)


_hatchet: Hatchet | None = None
MAX_WEBHOOK_BODY_BYTES = int(os.getenv("FORM_RECEIVER_MAX_WEBHOOK_BODY_BYTES", "262144"))
_trustedform_tasks: set[asyncio.Task[dict[str, object] | None]] = set()


async def _emit_captured_or_retry(lead_id: UUID, *, operation: str) -> None:
    if not await claim_capture_event_dispatch(lead_id):
        raise HTTPException(503, "event emission already in progress; will retry")
    try:
        if _hatchet is None:
            raise RuntimeError("hatchet client not initialized")
        await emit_lead_captured(_hatchet, lead_id)
        await mark_capture_event_emitted(lead_id)
    except Exception as e:
        await mark_capture_event_failed(lead_id)
        ERROR_SINK.report("form-receiver", operation, e, lead_id=str(lead_id))
        log.error("event.push_failed", operation=operation, error=str(e), lead_id=str(lead_id))
        raise HTTPException(503, "event emission failed; will retry") from e


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


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> str:
    return """
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>StormLead Privacy</title></head>
<body><h1>StormLead Privacy</h1>
<p>StormLead stores homeowner request details, contact information, service address, precise GPS location when shared, damage photo references, consent text, page URL, IP address, user agent, and campaign attribution to document opt-in and route tree-service leads.</p>
<p>AI-assisted review may summarize damage, urgency, visible safety risks, and buyer notes. Human review is required before routing power-line, injury, active-danger, roof-impact, or other high-risk requests.</p>
<p>Lead details may be shared with selected tree-service providers only for the submitted request. Submit an opt-out through <code>POST /v1/privacy/opt-out</code>. Matching future captures are suppressed before lead persistence.</p>
</body></html>
"""


@app.get("/terms", response_class=HTMLResponse)
async def terms() -> str:
    return """
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>StormLead Terms</title></head>
<body><h1>StormLead Terms</h1>
<p>StormLead is a matching/referral service and does not perform tree work. Any estimate or AI-assisted assessment is preliminary, not a guaranteed quote or safety determination.</p>
<p>For injuries, power lines, active fire, blocked emergency access, or immediate danger, stay away from the area and contact emergency services or the utility before contractor matching.</p>
<p>Local V1 operation is for technical validation. Paid delivery requires verified buyer terms, consent review, and explicit operator approval before public launch.</p>
</body></html>
"""


@app.post("/v1/privacy/opt-out")
async def opt_out(payload: SuppressionRequest) -> dict[str, str]:
    await record_suppression(
        phone_e164=payload.phone,
        email=payload.email,
        reason=payload.reason,
        source="privacy_endpoint",
    )
    return {"status": "suppressed"}


@app.post("/webhooks/formbricks")
async def formbricks_webhook(request: Request) -> dict[str, str]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as e:
            raise HTTPException(400, "invalid content-length header") from e
        if declared_size > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(413, "webhook body exceeds configured size limit")
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(413, "webhook body exceeds configured size limit")
    bind_correlation_id(request.headers.get("webhook-id"))
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
        log.info(
            "webhook.skipped_event",
            formbricks_event=envelope.event,
            webhook_id=envelope.webhookId,
        )
        return {"status": "skipped", "reason": f"event {envelope.event} not persisted"}

    # 3. extract consent
    try:
        extracted = extract_consent(envelope)
    except ConsentExtractionError as e:
        raise HTTPException(400, str(e)) from e

    ip = _client_ip(request)
    webhook_id = request.headers["webhook-id"]

    capture_status = await capture_status_for_webhook(webhook_id)
    if capture_status is not None:
        log.info(
            "webhook.retry_duplicate",
            webhook_id=webhook_id,
            lead_id=str(capture_status.lead_id),
            event_emitted=capture_status.event_emitted,
            audit_recorded=capture_status.audit_recorded,
        )
        if not capture_status.audit_recorded:
            await record_audit(
                webhook_id=webhook_id,
                lead_id=capture_status.lead_id,
                extracted=extracted,
                ip=ip,
                raw_payload=raw_body,
            )
        if not capture_status.event_emitted:
            await _emit_captured_or_retry(
                capture_status.lead_id,
                operation="emit_lead_captured_retry",
            )
        return {"status": "accepted-duplicate"}

    # 4. persist + emit
    try:
        lead_id, lead_created = await upsert_lead(extracted, ip=ip, webhook_id=webhook_id)
    except DuplicateLeadError as e:
        log.info(
            "webhook.duplicate_rejected",
            webhook_id=webhook_id,
            duplicate_lead_id=str(e.duplicate_lead_id),
            reason=e.reason,
            window_hours=e.window_hours,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "status": "duplicate",
                "reason": e.reason,
                "window_hours": e.window_hours,
            },
        ) from e
    except SuppressedLeadError as e:
        log.info(
            "webhook.suppressed",
            webhook_id=webhook_id,
            suppression_id=str(e.suppression_id),
            reason=e.reason,
        )
        return {"status": "suppressed"}
    if extracted.trustedform_cert_url:
        task = asyncio.create_task(verify_trustedform_cert(extracted.trustedform_cert_url))
        _trustedform_tasks.add(task)
        task.add_done_callback(_trustedform_tasks.discard)
    was_new = await record_audit(
        webhook_id=webhook_id,
        lead_id=lead_id,
        extracted=extracted,
        ip=ip,
        raw_payload=raw_body,
    )
    if was_new and lead_created:
        # Raise 5xx so Formbricks retries. The lead row stores capture_webhook_id
        # and dispatch status, so retries can refill missing audit and resume emit.
        await _emit_captured_or_retry(lead_id, operation="emit_lead_captured")
        emit_event("captured", lead_id=str(lead_id), service="form-receiver")
        emit_metric("funnel.captured", lead_id=str(lead_id), service="form-receiver")
        return {"status": "accepted", "lead_id": str(lead_id)}

    if was_new:
        log.info("webhook.duplicate_lead", webhook_id=webhook_id, lead_id=str(lead_id))
        return {"status": "accepted-duplicate"}

    log.info("webhook.duplicate", webhook_id=webhook_id, lead_id=str(lead_id))
    return {"status": "accepted-duplicate"}


@app.post("/webhooks/call-tracking")
async def call_tracking_webhook(request: Request) -> dict[str, object]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(413, "webhook body too large")
        except ValueError:
            raise HTTPException(400, "invalid content-length") from None

    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(413, "webhook body too large")
    try:
        verify_call_tracking_signature(
            raw_body=raw_body,
            signature=request.headers.get("x-call-tracking-signature"),
            timestamp=request.headers.get("x-call-tracking-timestamp"),
            secret=os.getenv("CALL_TRACKING_WEBHOOK_SECRET", ""),
        )
        event = CallTrackingEvent.model_validate_json(raw_body)
    except ReplayError as e:
        raise HTTPException(409, str(e)) from e
    except (MissingHeaderError, InvalidSignatureError) as e:
        raise HTTPException(401, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, "invalid call-tracking payload") from e

    async with get_session() as session:
        return await ingest_call_event(event, session)
