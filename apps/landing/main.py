from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from stormlead_core import (
    InvalidObjectKeyError,
    LocalFilesystemObjectStorage,
    ObjectNotFoundError,
)

app = FastAPI(title="stormlead landing")
templates = Jinja2Templates(directory="templates")

FORM_RECEIVER_URL = os.getenv("FORM_RECEIVER_URL", "http://form-receiver:8000").rstrip("/")
FORMBRICKS_WEBHOOK_SECRET = os.getenv("FORMBRICKS_WEBHOOK_SECRET", "whsec_change-me")
LOCAL_DNS_NAMES = {"form-receiver", "localhost", "host.docker.internal"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_UPLOAD_DEFAULT_DIR = PROJECT_ROOT / "testing" / "runs" / "local-demo-uploads"
DEFAULT_CONSENT_VERSION = "tree-damage-intake-v1"
HEIC_BRANDS = {
    b"heic",
    b"heix",
    b"hevc",
    b"hevx",
    b"heim",
    b"heis",
    b"hevm",
    b"hevs",
    b"mif1",
    b"msf1",
}
CONTENT_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}


def _local_demo_enabled() -> bool:
    return os.getenv("STORMLEAD_LOCAL_DEMO_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _local_demo_private_clients_allowed() -> bool:
    return os.getenv("STORMLEAD_LOCAL_DEMO_ALLOW_PRIVATE_CLIENTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@app.middleware("http")
async def local_demo_body_limit(request: Request, call_next: Any) -> Response:
    if request.url.path.startswith("/local-demo/") and request.method in {"POST", "PUT", "PATCH"}:
        max_body = (
            max(2, _positive_int_env("STORMLEAD_LOCAL_UPLOAD_MAX_FILES", 6))
            * _positive_int_env("STORMLEAD_LOCAL_UPLOAD_MAX_BYTES", 5 * 1024 * 1024)
            + 1024 * 1024
        )
        content_length = request.headers.get("content-length")
        if not content_length:
            return JSONResponse({"detail": "content-length is required"}, status_code=411)
        if content_length:
            try:
                if int(content_length) > max_body:
                    return JSONResponse({"detail": "upload request is too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "invalid content-length"}, status_code=400)
    return await call_next(request)


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


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _local_upload_dir() -> Path:
    configured = os.getenv("STORMLEAD_LOCAL_UPLOAD_DIR")
    path = Path(configured) if configured else LOCAL_UPLOAD_DEFAULT_DIR
    return path if path.is_absolute() else PROJECT_ROOT / path


def _local_object_storage() -> LocalFilesystemObjectStorage:
    return LocalFilesystemObjectStorage(_local_upload_dir(), allowed_prefixes=("local-demo/",))


def _formbricks_script_src() -> str:
    fallback = "/static/formbricks-placeholder.js"
    src = os.getenv("FORMBRICKS_SCRIPT_SRC", fallback).strip() or fallback
    if _local_demo_enabled():
        parsed = urlparse(src)
        if parsed.scheme or parsed.netloc or not src.startswith("/"):
            return fallback
    return src


def _consent_version() -> str:
    return (
        os.getenv("STORMLEAD_CONSENT_VERSION", DEFAULT_CONSENT_VERSION).strip()
        or DEFAULT_CONSENT_VERSION
    )


def _require_local_demo_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host == "testclient":
        return
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError as e:
        raise HTTPException(403, "local demo is only available from local clients") from e
    if client_ip.is_loopback:
        return
    if _local_demo_private_clients_allowed() and client_ip.is_private:
        return
    raise HTTPException(403, "local demo is only available from loopback clients")


def _damage_photo_extension_from_content(content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(content) >= 12 and content[0:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in HEIC_BRANDS:
        return ".heic"
    raise HTTPException(400, "damage photos must contain valid JPEG, PNG, WEBP, or HEIC bytes")


def _validated_damage_photo_keys(payload: dict[str, Any]) -> str:
    raw = _required_text(payload, "damage_photo_keys", max_length=2000)
    try:
        keys = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, "damage_photo_keys must be a JSON list") from e
    if not isinstance(keys, list):
        raise HTTPException(400, "damage_photo_keys must be a JSON list")

    storage = _local_object_storage()
    normalized_keys: list[str] = []
    for key in keys:
        if not isinstance(key, str) or not key:
            raise HTTPException(400, "damage_photo_keys must contain non-empty strings")
        try:
            normalized = storage.require_exists(key)
        except InvalidObjectKeyError as e:
            raise HTTPException(400, "damage_photo_keys must use local-demo upload keys") from e
        except ObjectNotFoundError as e:
            raise HTTPException(400, "uploaded damage photo is missing") from e
        normalized_keys.append(normalized)

    if len(normalized_keys) < 2:
        raise HTTPException(400, "at least two uploaded damage photos are required")
    return json.dumps(normalized_keys, separators=(",", ":"))


def _build_demo_envelope(payload: dict[str, Any], request: Request) -> tuple[str, dict[str, Any]]:
    now_ns = time.time_ns()
    scenario_id = uuid4().hex[:12]
    campaign_source = _optional_text(payload, "utm_source", max_length=128) or "local_landing_demo"
    campaign_id = (
        _optional_text(payload, "utm_campaign", max_length=128) or f"local_landing_{scenario_id}"
    )
    page_url = _optional_text(payload, "page_url", max_length=1000) or str(request.url_for("index"))
    user_agent = request.headers.get("user-agent", "StormLead Local Demo")[:500]
    consent_version = _consent_version()

    answers = {
        "name": _required_text(payload, "name", max_length=160),
        "phone": _required_text(payload, "phone", max_length=32),
        "email": _optional_text(payload, "email", max_length=255),
        "address_line1": _required_text(payload, "address_line1", max_length=255),
        "city": _required_text(payload, "city", max_length=128),
        "state": _required_text(payload, "state", max_length=2).upper(),
        "zip": _required_text(payload, "zip", max_length=10),
        "consent_text": _required_text(payload, "consent_text", max_length=1000),
        "consent_version": consent_version,
        "requested_service": _optional_text(payload, "requested_service", max_length=128)
        or "tree_removal",
        "damage_type": _required_text(payload, "damage_type", max_length=64),
        "urgency": _required_text(payload, "urgency", max_length=32),
        "damage_description": _required_text(payload, "damage_description", max_length=1000),
        "power_line_involved": _required_text(payload, "power_line_involved", max_length=8),
        "injury_reported": _required_text(payload, "injury_reported", max_length=8),
        "active_danger": _required_text(payload, "active_danger", max_length=8),
        "campaign_source": campaign_source,
        "campaign_id": campaign_id,
        "first_touch_source": campaign_source,
        "last_touch_source": campaign_source,
        "dwell_ms": 9000,
        "require_location_photo_verification": "true",
        "gps_latitude": _required_text(payload, "gps_latitude", max_length=32),
        "gps_longitude": _required_text(payload, "gps_longitude", max_length=32),
        "gps_accuracy_meters": _required_text(payload, "gps_accuracy_meters", max_length=32),
        "gps_captured_at": _required_text(payload, "gps_captured_at", max_length=64),
        "location_source": _optional_text(payload, "location_source", max_length=32)
        or "browser_gps",
        "location_confirmed_at": _required_text(payload, "location_confirmed_at", max_length=64),
        "damage_photo_keys": _validated_damage_photo_keys(payload),
    }

    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid"):
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
        hmac.new(
            _decode_webhook_secret(FORMBRICKS_WEBHOOK_SECRET), signed_payload, hashlib.sha256
        ).digest()
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

    @app.post("/local-demo/uploads")
    async def local_demo_uploads(
        request: Request,
        damage_photos: Annotated[list[UploadFile], File(...)],
    ) -> dict[str, Any]:
        _require_local_demo_request(request)
        if len(damage_photos) < 2:
            raise HTTPException(400, "at least two damage photos are required")

        max_files = max(2, _positive_int_env("STORMLEAD_LOCAL_UPLOAD_MAX_FILES", 6))
        if len(damage_photos) > max_files:
            raise HTTPException(400, f"at most {max_files} damage photos may be uploaded")

        max_bytes = _positive_int_env("STORMLEAD_LOCAL_UPLOAD_MAX_BYTES", 5 * 1024 * 1024)
        storage = _local_object_storage()
        batch_id = f"{int(time.time())}-{uuid4().hex[:12]}"
        prepared_photos: list[tuple[str, bytes, str]] = []

        for index, photo in enumerate(damage_photos, start=1):
            content = await photo.read(max_bytes + 1)
            if not content:
                raise HTTPException(400, "damage photos cannot be empty")
            if len(content) > max_bytes:
                raise HTTPException(400, f"damage photos must be {max_bytes} bytes or smaller")
            extension = _damage_photo_extension_from_content(content)
            prepared_photos.append(
                (
                    f"local-demo/{batch_id}/damage-{index}{extension}",
                    content,
                    CONTENT_TYPE_BY_EXTENSION[extension],
                )
            )

        try:
            stored_photos = [
                await asyncio.to_thread(storage.put_bytes, key, content, content_type=content_type)
                for key, content, content_type in prepared_photos
            ]
        except OSError as e:
            raise HTTPException(500, "local damage photo upload failed") from e

        return {
            "photo_keys": [photo.key for photo in stored_photos],
            "photo_count": len(stored_photos),
            "photos": [
                {
                    "key": photo.key,
                    "content_type": photo.content_type,
                    "size_bytes": photo.size_bytes,
                    "sha256": photo.sha256,
                }
                for photo in stored_photos
            ],
        }

    @app.post("/local-demo/lead")
    async def local_demo_lead(request: Request) -> dict[str, Any]:
        _require_local_demo_request(request)
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
        if (key.startswith("utm_") or key == "gclid") and value:
            hidden_fields[key] = value
    hidden_fields.setdefault("consent_version", _consent_version())

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "formbricks_env_id": os.getenv("FORMBRICKS_ENV_ID", "local-env"),
            "formbricks_survey_id": os.getenv("FORMBRICKS_SURVEY_ID", "local-survey"),
            "formbricks_script_src": _formbricks_script_src(),
            "hidden_fields": hidden_fields,
            "local_demo_enabled": _local_demo_enabled(),
        },
    )
