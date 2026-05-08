from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import httpx
import ping_post.api as api_module
import pytest


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_module.app), base_url="http://test"
    ) as test_client:
        yield test_client


def _test_buyer(buyer_id, api_key: str) -> api_module.BuyerRow:
    return api_module.BuyerRow(
        id=buyer_id,
        name="Deposit Buyer",
        company="Deposit Co",
        contact_email="deposit@example.com",
        contact_phone_e164="+13215550000",
        status="active",
        api_key=api_key,
        webhook_url="http://localhost:9999/webhook",
        bid_per_lead_t1_t2=Decimal("45.00"),
        bid_per_lead_t3=Decimal("25.00"),
        bid_per_call=Decimal("15.00"),
        filter_expression="true",
        daily_cap=10,
        monthly_budget=Decimal("1000.00"),
        deposit_balance=Decimal("0.00"),
        lifetime_spend=Decimal("0.00"),
    )


class FakeBuyerSession:
    def __init__(self, buyer: api_module.BuyerRow) -> None:
        self.buyer = buyer
        self.added: list[object] = []

    async def __aenter__(self) -> FakeBuyerSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, model: object, row_id: object) -> api_module.BuyerRow:
        assert model is api_module.BuyerRow
        assert row_id == self.buyer.id
        return self.buyer

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_operator_gate_blocks_admin_api_when_required(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")

    response = await client.get("/v1/admin/kpis")
    assert response.status_code == 401
    assert response.json()["detail"] == "operator token required for admin or funding operations"

    health = await client.get("/healthz")
    assert health.status_code == 200


async def test_forwarded_for_does_not_bypass_operator_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("STORMLEAD_LOCAL_AUTH_BYPASS", raising=False)
    transport = httpx.ASGITransport(app=api_module.app, client=("203.0.113.10", 45123))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.get(
            "/v1/admin/kpis",
            headers={"x-forwarded-for": "127.0.0.1"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "operator token required for admin or funding operations"


async def test_operator_deposit_does_not_require_buyer_api_key_when_strict_gates(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.post(
        f"/v1/buyers/{buyer_id}/deposits",
        json={"amount_cents": 75000, "external_reference": "operator-only-test"},
        headers={"Authorization": "Bearer test-operator-token"},
    )

    assert response.status_code == 200
    assert response.json()["deposit_balance_cents"] == 75000
    assert fake_session.added


async def test_buyer_wallet_requires_valid_api_key_when_strict_gate(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")

    buyer_id = uuid4()
    buyer_key = f"buyer-{buyer_id.hex}"
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, buyer_key))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    missing = await client.get(f"/v1/buyers/{buyer_id}/wallet")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "valid buyer API key required"

    wrong = await client.get(
        f"/v1/buyers/{buyer_id}/wallet",
        headers={"Authorization": f"Bearer wrong-{buyer_id.hex}"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "valid buyer API key required"

    valid = await client.get(
        f"/v1/buyers/{buyer_id}/wallet",
        headers={"Authorization": f"Bearer {buyer_key}"},
    )
    assert valid.status_code == 200
    assert valid.json()["buyer_id"] == str(buyer_id)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires live DB")
async def test_create_buyer_returns_id(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/buyers",
        json={
            "name": "Integration Buyer",
            "company": "Integration Tree",
            "contact_email": "ops@integration.example",
            "contact_phone_e164": "+13215550001",
            "webhook_url": "http://localhost:9999/buyer",
            "webhook_secret": "test-secret-32chars-minimum-ok",
            "bid_per_lead_t1_t2": "75.00",
            "bid_per_lead_t3": "175.00",
            "bid_per_call": "100.00",
            "filter_expression": "lead.state == 'FL'",
            "target_zips": ["32801"],
            "exclusive_zips": [],
        },
    )
    assert response.status_code in {200, 201}
    assert "buyer_id" in response.json()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires live DB")
async def test_duplicate_exclusive_zip_returns_409(client: httpx.AsyncClient) -> None:
    payload = {
        "name": "Integration Buyer",
        "company": "Integration Tree",
        "contact_email": "ops@integration.example",
        "contact_phone_e164": "+13215550001",
        "webhook_url": "http://localhost:9999/buyer",
        "webhook_secret": "test-secret-32chars-minimum-ok",
        "bid_per_lead_t1_t2": "75.00",
        "bid_per_lead_t3": "175.00",
        "bid_per_call": "100.00",
        "filter_expression": "lead.state == 'FL'",
        "target_zips": ["32801"],
        "exclusive_zips": ["32801"],
    }
    first = await client.post("/v1/buyers", json=payload)
    assert first.status_code in {200, 201, 409}
    second = await client.post("/v1/buyers", json={**payload, "contact_phone_e164": "+13215550002"})
    assert second.status_code in {200, 201, 409}
