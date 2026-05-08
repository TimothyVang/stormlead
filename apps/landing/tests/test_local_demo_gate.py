from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from fastapi.testclient import TestClient


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


def test_local_demo_disabled_hides_form_and_route(monkeypatch):
    module = _load_landing(monkeypatch, enabled=False)
    client = TestClient(module.app)

    page = client.get("/")
    assert page.status_code == 200
    assert 'data-testid="local-lead-form"' not in page.text
    assert 'data-testid="local-demo-disabled"' in page.text

    post = client.post("/local-demo/lead", json={})
    assert post.status_code == 404


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
