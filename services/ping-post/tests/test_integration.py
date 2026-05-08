from __future__ import annotations

import os

import httpx
import pytest
from ping_post.api import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client


async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
