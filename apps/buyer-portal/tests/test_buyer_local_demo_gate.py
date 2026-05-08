from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from fastapi.testclient import TestClient


def _load_buyer_portal(monkeypatch, *, enabled: bool) -> ModuleType:
    app_dir = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(app_dir)
    if enabled:
        monkeypatch.setenv("STORMLEAD_LOCAL_DEMO_ENABLED", "true")
    else:
        monkeypatch.delenv("STORMLEAD_LOCAL_DEMO_ENABLED", raising=False)

    module_name = f"buyer_portal_main_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, app_dir / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_demo_disabled_hides_deposit_form_and_route(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)

    async def fake_ping_post(path: str, api_key: str | None, **kwargs):
        if path.endswith("/wallet"):
            return {
                "buyer_id": "buyer-test",
                "deposit_balance_cents": 0,
                "lifetime_spend_cents": 0,
                "monthly_budget_cents": 0,
                "daily_cap": 10,
            }
        return {"delivered_leads": [], "buyer": {"buyer_id": "buyer-test"}}

    monkeypatch.setattr(module, "_ping_post", fake_ping_post)
    client = TestClient(module.app)

    page = client.get(
        "/buyer-portal/wallet",
        headers={"cookie": "buyer_id=buyer-test; buyer_api_key=local-test"},
    )
    assert page.status_code == 200
    assert 'data-testid="wallet-deposit-form"' not in page.text
    assert 'data-testid="wallet-deposit-disabled"' in page.text

    post = client.post(
        "/buyer-portal/wallet/deposit",
        data={"amount_cents": "50000", "external_reference": "test"},
        headers={"cookie": "buyer_id=buyer-test; buyer_api_key=local-test"},
    )
    assert post.status_code == 404
