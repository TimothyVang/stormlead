from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def _load_landing(monkeypatch, *, enabled: bool) -> ModuleType:
    app_dir = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(app_dir)
    if enabled:
        monkeypatch.setenv("STORMLEAD_LOCAL_DEMO_ENABLED", "true")
    else:
        monkeypatch.delenv("STORMLEAD_LOCAL_DEMO_ENABLED", raising=False)

    module_name = f"landing_main_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, app_dir / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _complete_lead_payload(photo_keys: list[str]) -> dict[str, str]:
    return {
        "name": "Synthetic Homeowner",
        "phone": "+15125550123",
        "address_line1": "100 Main St",
        "city": "Baton Rouge",
        "state": "LA",
        "zip": "70802",
        "consent_text": "I agree to be contacted.",
        "damage_type": "fallen_tree",
        "urgency": "same_day",
        "damage_description": "Fallen tree across driveway.",
        "power_line_involved": "false",
        "injury_reported": "false",
        "active_danger": "false",
        "gps_latitude": "30.4515",
        "gps_longitude": "-91.1871",
        "gps_accuracy_meters": "25",
        "gps_captured_at": "2026-05-11T00:00:00Z",
        "location_confirmed_at": "2026-05-11T00:00:01Z",
        "damage_photo_keys": json.dumps(photo_keys),
    }


def _local_demo_request(headers: list[tuple[bytes, bytes]]) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/local-demo/uploads",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        },
        receive,
    )


async def _ok_response(_request: Request) -> Response:
    return Response("ok")


def test_local_demo_disabled_hides_form_and_route(monkeypatch):
    module = _load_landing(monkeypatch, enabled=False)
    client = TestClient(module.app)

    page = client.get("/")
    assert page.status_code == 200
    assert 'data-testid="local-lead-form"' not in page.text
    assert 'data-testid="local-demo-disabled"' in page.text

    post = client.post("/local-demo/lead", json={})
    assert post.status_code == 404

    uploads = client.post("/local-demo/uploads", files=[])
    assert uploads.status_code == 404


def test_receiver_guard_rejects_link_local_metadata(monkeypatch):
    module = _load_landing(monkeypatch, enabled=True)

    assert not module._is_allowed_local_receiver("http://169.254.169.254/latest/meta-data")
    assert not module._is_allowed_local_receiver("http://[fe80::1]/webhooks/formbricks")
    assert not module._is_allowed_local_receiver("http://10.0.0.1/webhooks/formbricks")
    assert not module._is_allowed_local_receiver("http://172.16.0.1/webhooks/formbricks")
    assert not module._is_allowed_local_receiver("http://192.168.1.1/webhooks/formbricks")
    assert module._is_allowed_local_receiver("http://127.0.0.1:8002")
    assert module._is_allowed_local_receiver("http://[::1]:8002")
    assert module._is_allowed_local_receiver("http://form-receiver:8000")


def test_local_demo_forces_local_formbricks_script(monkeypatch):
    monkeypatch.setenv("FORMBRICKS_SCRIPT_SRC", "https://forms.example.test/formbricks.js")
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    page = client.get("/")

    assert page.status_code == 200
    assert 'src="/static/formbricks-placeholder.js"' in page.text
    assert "https://forms.example.test" not in page.text


def test_louisiana_landing_preserves_google_ads_attribution(monkeypatch):
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    page = client.get(
        "/louisiana-storm-tree-removal"
        "?utm_source=google_ads&utm_medium=paid_search"
        "&utm_campaign=la-canary&gclid=gclid12345678"
    )

    assert page.status_code == 200
    assert "Louisiana hurricane response" in page.text
    assert 'name="city" value="New Orleans"' in page.text
    assert 'name="state" value="LA"' in page.text
    assert 'name="zip" value="70112"' in page.text
    assert 'name="utm_source" value="google_ads"' in page.text
    assert 'name="utm_medium" value="paid_search"' in page.text
    assert 'name="utm_campaign" value="la-canary"' in page.text
    assert 'name="gclid" value="gclid12345678"' in page.text


def test_local_demo_upload_requires_content_length(monkeypatch):
    module = _load_landing(monkeypatch, enabled=True)

    response = asyncio.run(module.local_demo_body_limit(_local_demo_request([]), _ok_response))

    assert response.status_code == 411


def test_local_demo_upload_rejects_oversized_content_length(monkeypatch):
    monkeypatch.setenv("STORMLEAD_LOCAL_UPLOAD_MAX_FILES", "2")
    monkeypatch.setenv("STORMLEAD_LOCAL_UPLOAD_MAX_BYTES", "10")
    module = _load_landing(monkeypatch, enabled=True)

    response = asyncio.run(
        module.local_demo_body_limit(
            _local_demo_request([(b"content-length", b"1048600")]),
            _ok_response,
        )
    )

    assert response.status_code == 413


def test_local_demo_requires_location_and_photo_metadata(monkeypatch):
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    response = client.post(
        "/local-demo/lead",
        json={
            "name": "Synthetic Homeowner",
            "phone": "+15125550123",
            "address_line1": "100 Main St",
            "city": "Baton Rouge",
            "state": "LA",
            "zip": "70802",
            "consent_text": "I agree to be contacted.",
            "damage_type": "fallen_tree",
            "urgency": "same_day",
            "damage_description": "Fallen tree across driveway.",
            "power_line_involved": "false",
            "injury_reported": "false",
            "active_danger": "false",
        },
    )

    assert response.status_code == 400
    assert "gps_latitude is required" in response.json()["detail"]


def test_local_demo_uploads_damage_photos_to_local_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("STORMLEAD_LOCAL_UPLOAD_DIR", str(tmp_path))
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    response = client.post(
        "/local-demo/uploads",
        files=[
            ("damage_photos", ("wide-damage.jpg", JPEG_BYTES, "image/jpeg")),
            ("damage_photos", ("close-damage.png", PNG_BYTES, "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["photo_count"] == 2
    assert len(body["photo_keys"]) == 2
    assert body["photos"][0]["content_type"] == "image/jpeg"
    assert body["photos"][0]["size_bytes"] == len(JPEG_BYTES)
    assert len(body["photos"][0]["sha256"]) == 64
    assert all("wide-damage" not in key and "close-damage" not in key for key in body["photo_keys"])
    assert (tmp_path / body["photo_keys"][0]).read_bytes() == JPEG_BYTES
    assert (tmp_path / body["photo_keys"][1]).read_bytes() == PNG_BYTES


def test_local_demo_rejects_unuploaded_photo_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("STORMLEAD_LOCAL_UPLOAD_DIR", str(tmp_path))
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    response = client.post(
        "/local-demo/lead",
        json=_complete_lead_payload(
            ["local-demo/missing/wide.jpg", "local-demo/missing/close.jpg"]
        ),
    )

    assert response.status_code == 400
    assert "uploaded damage photo is missing" in response.json()["detail"]


def test_local_demo_uploads_reject_non_image_files(monkeypatch, tmp_path):
    monkeypatch.setenv("STORMLEAD_LOCAL_UPLOAD_DIR", str(tmp_path))
    module = _load_landing(monkeypatch, enabled=True)
    client = TestClient(module.app)

    response = client.post(
        "/local-demo/uploads",
        files=[
            ("damage_photos", ("fake-wide.jpg", b"not an image", "image/jpeg")),
            ("damage_photos", ("close-damage.jpg", JPEG_BYTES, "image/jpeg")),
        ],
    )

    assert response.status_code == 400
    assert "valid JPEG, PNG, WEBP, or HEIC bytes" in response.json()["detail"]
