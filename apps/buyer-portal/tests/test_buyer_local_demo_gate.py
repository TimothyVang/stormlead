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


def test_login_rejects_invalid_buyer_api_key(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)

    async def fake_ping_post(path: str, api_key: str | None, **kwargs):
        assert path == "/v1/buyers/buyer-test/wallet"
        assert api_key == "bad-key"
        return {"error": "unauthorized", "status_code": 401}

    monkeypatch.setattr(module, "_ping_post", fake_ping_post)
    client = TestClient(module.app)

    response = client.post(
        "/login",
        data={"buyer_id": "buyer-test", "buyer_api_key": "bad-key"},
    )
    assert response.status_code == 401
    assert "Buyer ID or API key was rejected" in response.text
    assert "set-cookie" not in response.headers


def test_wallet_page_shows_readiness_reconciliation_and_key_rotation(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)

    async def fake_ping_post(path: str, api_key: str | None, **kwargs):
        assert api_key == "buyer-key"
        if path.endswith("/wallet"):
            return {
                "buyer_id": "buyer-test",
                "deposit_balance_cents": 75000,
                "lifetime_spend_cents": 12500,
                "monthly_budget_cents": 100000,
                "daily_cap": 10,
            }
        if path.endswith("/daily-report"):
            return {
                "wallet": {
                    "below_threshold": True,
                    "recommended_refill_cents": 25000,
                },
                "delivered_leads": [],
            }
        if path.endswith("/wallet/reconciliation"):
            return {
                "ledger": {
                    "signed_total_cents": 70000,
                    "mutable_balance_cents": 75000,
                    "delta_cents": 5000,
                    "reconciled": False,
                    "recent_funding_events": [],
                },
                "payment_readiness": {
                    "local_refills_ready": True,
                    "live_payments_approved": False,
                },
            }
        return {
            "buyer_id": "buyer-test",
            "deposit_balance_cents": 75000,
            "low_balance_threshold_cents": 100000,
            "onboarding_readiness": {
                "autopilot_ready": False,
                "missing_requirements": ["service_ready", "zip_ready"],
                "coverage_zips": ["32801"],
            },
        }

    monkeypatch.setattr(module, "_ping_post", fake_ping_post)
    client = TestClient(module.app)

    page = client.get(
        "/buyer-portal/wallet",
        headers={"cookie": "buyer_id=buyer-test; buyer_api_key=buyer-key"},
    )

    assert page.status_code == 200
    assert 'data-testid="buyer-readiness-panel"' in page.text
    assert 'data-testid="api-key-rotation-panel"' in page.text
    assert "Existing integrations using the old key will fail immediately" in page.text
    assert "service_ready" in page.text
    assert "zip_ready" in page.text
    assert "Service coverage configured" in page.text
    assert "Live Stripe remains approval-gated" in page.text
    assert "Balance $750.00 vs. threshold $1,000.00" in page.text
    assert "Difference: $50.00" in page.text
    assert "operator reconciliation before launch" in page.text


def test_wallet_requires_buyer_id_and_api_key_cookies(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)
    client = TestClient(module.app, follow_redirects=False)

    page = client.get(
        "/buyer-portal/wallet",
        headers={"cookie": "buyer_id=buyer-test"},
    )

    assert page.status_code == 303
    assert page.headers["location"] == "/login"


def test_api_key_rotation_updates_cookie_and_shows_new_key_once(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)
    calls: list[tuple[str, str | None, str]] = []

    async def fake_ping_post(path: str, api_key: str | None, **kwargs):
        method = str(kwargs.get("method", "GET"))
        calls.append((path, api_key, method))
        if path.endswith("/api-key/rotate"):
            assert api_key == "old-key"
            assert method == "POST"
            return {"api_key": "new-key", "buyer_id": "buyer-test"}
        assert api_key == "new-key"
        if path.endswith("/wallet"):
            return {
                "buyer_id": "buyer-test",
                "deposit_balance_cents": 100000,
                "lifetime_spend_cents": 0,
                "monthly_budget_cents": 100000,
                "daily_cap": 10,
            }
        if path.endswith("/daily-report"):
            return {"wallet": {"below_threshold": False, "recommended_refill_cents": 0}}
        if path.endswith("/wallet/reconciliation"):
            return {
                "ledger": {
                    "signed_total_cents": 100000,
                    "mutable_balance_cents": 100000,
                    "delta_cents": 0,
                    "reconciled": True,
                    "recent_funding_events": [],
                },
                "payment_readiness": {
                    "local_refills_ready": True,
                    "live_payments_approved": False,
                },
            }
        return {
            "buyer_id": "buyer-test",
            "onboarding_readiness": {
                "autopilot_ready": True,
                "missing_requirements": [],
                "coverage_zips": ["32801"],
            },
        }

    monkeypatch.setattr(module, "_ping_post", fake_ping_post)
    client = TestClient(module.app)
    client.cookies.set("buyer_id", "buyer-test")
    client.cookies.set("buyer_api_key", "old-key")

    response = client.post("/buyer-portal/api-key/rotate")

    assert response.status_code == 200
    assert 'data-testid="api-key-rotated"' in response.text
    assert "new-key" in response.text
    assert "buyer_api_key=new-key" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert calls[0] == ("/v1/buyers/buyer-test/api-key/rotate", "old-key", "POST")


def test_api_key_rotation_backend_error_is_visible(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)

    async def fake_ping_post(path: str, api_key: str | None, **kwargs):
        if path.endswith("/api-key/rotate"):
            return {"error": "rotation denied", "status_code": 401}
        if path.endswith("/wallet"):
            return {
                "buyer_id": "buyer-test",
                "deposit_balance_cents": 0,
                "lifetime_spend_cents": 0,
                "monthly_budget_cents": 0,
                "daily_cap": 10,
            }
        if path.endswith("/daily-report"):
            return {"wallet": {"below_threshold": False, "recommended_refill_cents": 0}}
        if path.endswith("/wallet/reconciliation"):
            return {
                "ledger": {
                    "signed_total_cents": 0,
                    "mutable_balance_cents": 0,
                    "delta_cents": 0,
                    "reconciled": True,
                    "recent_funding_events": [],
                },
                "payment_readiness": {
                    "local_refills_ready": True,
                    "live_payments_approved": True,
                },
            }
        return {
            "buyer_id": "buyer-test",
            "deposit_balance_cents": 0,
            "low_balance_threshold_cents": 0,
            "onboarding_readiness": {
                "autopilot_ready": True,
                "missing_requirements": [],
                "coverage_zips": [],
            },
        }

    monkeypatch.setattr(module, "_ping_post", fake_ping_post)
    client = TestClient(module.app)
    client.cookies.set("buyer_id", "buyer-test")
    client.cookies.set("buyer_api_key", "old-key")

    response = client.post("/buyer-portal/api-key/rotate")

    assert response.status_code == 200
    assert 'data-testid="api-key-result"' in response.text
    assert 'data-status="error"' in response.text
    assert "rotation denied" in response.text
    assert "Live payments approved" in response.text


def test_api_key_rotation_requires_login(monkeypatch):
    module = _load_buyer_portal(monkeypatch, enabled=False)
    client = TestClient(module.app, follow_redirects=False)

    response = client.post("/buyer-portal/api-key/rotate")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
