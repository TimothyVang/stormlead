from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI(title="stormlead landing")
templates = Jinja2Templates(directory="templates")

FORM_RECEIVER_URL = os.getenv("FORM_RECEIVER_URL", "http://form-receiver:8000").rstrip("/")
FORMBRICKS_WEBHOOK_SECRET = os.getenv("FORMBRICKS_WEBHOOK_SECRET", "whsec_change-me")
LOCAL_DNS_NAMES = {"form-receiver", "localhost", "host.docker.internal"}


def _local_demo_enabled() -> bool:
    return os.getenv("STORMLEAD_LOCAL_DEMO_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/static/formbricks-placeholder.js")
async def formbricks_placeholder() -> Response:
    script = """
window.formbricks = window.formbricks || {
  init: function(config) {
    window.formbricksInitialized = true;
    window.formbricksLastConfig = config;
  }
};
window.formbricks.init(window.formbricksConfig || {});
"""
    return Response(script, media_type="application/javascript")


def _decode_webhook_secret(secret: str) -> bytes:
    body = secret.removeprefix("whsec_")
    return base64.b64decode(body + ("=" * (-len(body) % 4)))


def _is_allowed_local_receiver(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()
    if hostname in LOCAL_DNS_NAMES or hostname.endswith(".localhost"):
        return True

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
        return False
    return False


def _required_text(payload: dict[str, Any], key: str, *, max_length: int = 500) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(400, f"{key} is required")
    return value.strip()[:max_length]


def _optional_text(payload: dict[str, Any], key: str, *, max_length: int = 500) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def _build_demo_envelope(payload: dict[str, Any], request: Request) -> tuple[str, dict[str, Any]]:
    now_ns = time.time_ns()
    scenario_id = uuid4().hex[:12]
    campaign_source = _optional_text(payload, "utm_source", max_length=128) or "local_landing_demo"
    campaign_id = _optional_text(payload, "utm_campaign", max_length=128) or f"local_landing_{scenario_id}"
    page_url = _optional_text(payload, "page_url", max_length=1000) or str(request.url_for("index"))
    user_agent = request.headers.get("user-agent", "StormLead Local Demo")[:500]

    answers = {
        "name": _required_text(payload, "name", max_length=160),
        "phone": _required_text(payload, "phone", max_length=32),
        "email": _optional_text(payload, "email", max_length=255),
        "address_line1": _required_text(payload, "address_line1", max_length=255),
        "city": _required_text(payload, "city", max_length=128),
        "state": _required_text(payload, "state", max_length=2).upper(),
        "zip": _required_text(payload, "zip", max_length=10),
        "consent_text": _required_text(payload, "consent_text", max_length=1000),
        "requested_service": _optional_text(payload, "requested_service", max_length=128)
        or "tree_removal",
        "campaign_source": campaign_source,
        "campaign_id": campaign_id,
        "first_touch_source": campaign_source,
        "last_touch_source": campaign_source,
        "dwell_ms": 9000,
    }

    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"):
        value = _optional_text(payload, key, max_length=255)
        if value:
            answers[key] = value

    webhook_id = f"landing-local-{now_ns}-{scenario_id}"
    return webhook_id, {
        "event": "responseFinished",
        "webhookId": webhook_id,
        "data": {
            "id": f"resp-landing-local-{now_ns}-{scenario_id}",
            "surveyId": os.getenv("FORMBRICKS_SURVEY_ID", "local-survey"),
            "data": answers,
            "ttc": {"name": 1400, "phone": 2100, "consent_text": 5500},
            "contactAttributes": {
                "campaign_source": campaign_source,
                "campaign_id": campaign_id,
            },
            "meta": {"url": page_url, "userAgent": user_agent},
            "finished": True,
        },
    }


def _post_form_receiver(webhook_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    if not _is_allowed_local_receiver(FORM_RECEIVER_URL):
        raise HTTPException(
            400,
            "local demo can only forward to loopback, localhost, or approved local Docker DNS names",
        )

    raw_body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signed_payload = f"{webhook_id}.{timestamp}.".encode() + raw_body
    signature = base64.b64encode(
        hmac.new(_decode_webhook_secret(FORMBRICKS_WEBHOOK_SECRET), signed_payload, hashlib.sha256).digest()
    ).decode("ascii")
    request = UrlRequest(  # noqa: S310 - receiver URL is restricted to explicit local targets.
        f"{FORM_RECEIVER_URL}/webhooks/formbricks",
        data=raw_body,
        headers={
            "content-type": "application/json",
            "webhook-id": webhook_id,
            "webhook-timestamp": timestamp,
            "webhook-signature": f"v1,{signature}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - explicit local targets only.
            response_body = response.read().decode("utf-8")
            return json.loads(response_body) if response_body else {"status": "accepted"}
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise HTTPException(e.code, detail or "form-receiver rejected the local demo lead") from e
    except URLError as e:
        raise HTTPException(502, f"form-receiver unavailable: {e.reason}") from e


if _local_demo_enabled():

    @app.post("/local-demo/lead")
    async def local_demo_lead(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except json.JSONDecodeError as e:
            raise HTTPException(400, "malformed JSON body") from e
        if not isinstance(payload, dict):
            raise HTTPException(400, "JSON object body is required")

        webhook_id, envelope = _build_demo_envelope(payload, request)
        return await asyncio.to_thread(_post_form_receiver, webhook_id, envelope)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    hidden_fields: dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("utm_") and value:
            hidden_fields[key] = value

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "formbricks_env_id": os.getenv("FORMBRICKS_ENV_ID", "local-env"),
            "formbricks_survey_id": os.getenv("FORMBRICKS_SURVEY_ID", "local-survey"),
            "formbricks_script_src": os.getenv(
                "FORMBRICKS_SCRIPT_SRC", "/static/formbricks-placeholder.js"
            ),
            "hidden_fields": hidden_fields,
            "local_demo_enabled": _local_demo_enabled(),
        },
    )
