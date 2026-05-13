from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
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


def _buyer_create_payload(webhook_url: str) -> dict[str, object]:
    return {
        "name": "Integration Buyer",
        "company": "Integration Tree",
        "contact_email": "ops@integration.example",
        "contact_phone_e164": "+13215550001",
        "webhook_url": webhook_url,
        "webhook_secret": "test-secret-32chars-minimum-ok",
        "bid_per_lead_t1_t2": "75.00",
        "bid_per_lead_t3": "175.00",
        "bid_per_call": "100.00",
        "filter_expression": "lead.state == 'FL'",
        "target_zips": ["32801"],
        "exclusive_zips": [],
    }


class FakeBuyerSession:
    def __init__(self, buyer: api_module.BuyerRow) -> None:
        self.buyer = buyer
        self.added: list[api_module.BillingEvent | api_module.PaymentWebhookEvent] = []
        self.existing_payment_event: api_module.BillingEvent | None = None
        self.exit_exc_types: list[object | None] = []
        self.executed_statements: list[str] = []
        self.get_kwargs: list[dict[str, object]] = []
        self.scalar_value = 0

    async def __aenter__(self) -> FakeBuyerSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.exit_exc_types.append(args[0] if args else None)
        return None

    async def get(self, model: object, row_id: object, **_kwargs: object) -> api_module.BuyerRow:
        self.get_kwargs.append(_kwargs)
        assert model is api_module.BuyerRow
        assert row_id == self.buyer.id
        return self.buyer

    def add(self, row: api_module.BillingEvent | api_module.PaymentWebhookEvent) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        for row in self.added:
            if row.id is None:
                row.id = uuid4()
            if row.created_at is None:
                row.created_at = datetime.now(UTC)
        return None

    async def execute(self, _statement: object, *_args: object, **_kwargs: object) -> object:
        self.executed_statements.append(str(_statement))
        rows = [self.existing_payment_event] if self.existing_payment_event is not None else []
        return FakeExecuteResult(rows)

    async def scalar(self, _statement: object) -> int:
        return self.scalar_value


class FakeExecuteResult:
    def __init__(self, rows: list[api_module.BillingEvent]) -> None:
        self.rows = rows

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self.rows)


class FakeScalarResult:
    def __init__(self, rows: list[api_module.BillingEvent]) -> None:
        self.rows = rows

    def first(self) -> api_module.BillingEvent | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[api_module.BillingEvent]:
        return self.rows


class FakeExceptionQueueSession:
    def __init__(self, execute_rows: list[list[api_module.ExceptionQueueItem]]) -> None:
        self.execute_rows = execute_rows
        self.added: list[api_module.ExceptionQueueItem] = []
        self.flushed = False

    async def __aenter__(self) -> FakeExceptionQueueSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> object:
        rows = self.execute_rows.pop(0) if self.execute_rows else []
        return FakeExceptionQueueExecuteResult(rows)

    def add(self, row: api_module.ExceptionQueueItem) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed = True


class FakeExceptionQueueExecuteResult:
    def __init__(self, rows: list[api_module.ExceptionQueueItem]) -> None:
        self.rows = rows

    def scalars(self) -> FakeExceptionQueueScalarResult:
        return FakeExceptionQueueScalarResult(self.rows)


class FakeExceptionQueueScalarResult:
    def __init__(self, rows: list[api_module.ExceptionQueueItem]) -> None:
        self.rows = rows

    def first(self) -> api_module.ExceptionQueueItem | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[api_module.ExceptionQueueItem]:
        return self.rows


class FakeBudgetActionSession:
    def __init__(self, rows: list[api_module.BudgetActionLog]) -> None:
        self.rows = rows

    async def __aenter__(self) -> FakeBudgetActionSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> object:
        return FakeBudgetActionExecuteResult(self.rows)


class FakeBudgetActionExecuteResult:
    def __init__(self, rows: list[api_module.BudgetActionLog]) -> None:
        self.rows = rows

    def scalars(self) -> FakeBudgetActionScalarResult:
        return FakeBudgetActionScalarResult(self.rows)


class FakeBudgetActionScalarResult:
    def __init__(self, rows: list[api_module.BudgetActionLog]) -> None:
        self.rows = rows

    def all(self) -> list[api_module.BudgetActionLog]:
        return self.rows


class FakeLearningProposalSession:
    def __init__(self, rows: list[api_module.LearningProposal]) -> None:
        self.rows = rows

    async def __aenter__(self) -> FakeLearningProposalSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> object:
        return FakeLearningProposalExecuteResult(self.rows)


class FakeLearningProposalExecuteResult:
    def __init__(self, rows: list[api_module.LearningProposal]) -> None:
        self.rows = rows

    def scalars(self) -> FakeLearningProposalScalarResult:
        return FakeLearningProposalScalarResult(self.rows)


class FakeLearningProposalScalarResult:
    def __init__(self, rows: list[api_module.LearningProposal]) -> None:
        self.rows = rows

    def all(self) -> list[api_module.LearningProposal]:
        return self.rows


class FakeEmptySession:
    def __init__(self) -> None:
        self.exit_exc_types: list[object | None] = []

    async def __aenter__(self) -> FakeEmptySession:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.exit_exc_types.append(args[0] if args else None)
        return None


class FakeLeadReviewSession:
    def __init__(self, lead_id) -> None:
        self.lead = SimpleNamespace(id=lead_id, status="qualified", hold_for_review=True)
        self.flushed = False

    async def __aenter__(self) -> FakeLeadReviewSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, model: object, row_id: object) -> object | None:
        assert model is api_module.LeadRow
        return self.lead if row_id == self.lead.id else None

    async def flush(self) -> None:
        self.flushed = True


class FakeAdsSession:
    def __init__(self, rows: list[tuple[object, object]], wallet_runway_cents: int) -> None:
        self.rows = rows
        self.wallet_runway_cents = wallet_runway_cents

    async def __aenter__(self) -> FakeAdsSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, _statement: object) -> FakeAdsExecuteResult:
        return FakeAdsExecuteResult(self.rows)

    async def scalar(self, _statement: object) -> int:
        return self.wallet_runway_cents


class FakeAdsExecuteResult:
    def __init__(self, rows: list[tuple[object, object]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[object, object]]:
        return self.rows


class FakeLaunchReadinessSession:
    def __init__(self, scalar_values: list[int], buyers: list[object]) -> None:
        self.scalar_values = scalar_values
        self.buyers = buyers

    async def __aenter__(self) -> FakeLaunchReadinessSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalar(self, _statement: object) -> int:
        return self.scalar_values.pop(0)

    async def execute(self, _statement: object) -> FakeLaunchReadinessExecuteResult:
        return FakeLaunchReadinessExecuteResult(self.buyers)


class FakeLaunchReadinessExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> FakeLaunchReadinessScalarResult:
        return FakeLaunchReadinessScalarResult(self.rows)


class FakeLaunchReadinessScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return list(self.rows)


def _launch_ready_buyer(index: int = 0) -> api_module.BuyerRow:
    return api_module.BuyerRow(
        id=uuid4(),
        name=f"Launch Buyer {index}",
        company=f"Launch Tree {index}",
        contact_email=f"launch{index}@example.com",
        contact_phone_e164="+13215550100",
        status=api_module.BuyerStatus.ACTIVE.value,
        sales_stage=api_module.BuyerSalesStage.FUNDED.value,
        api_key=f"launch-api-key-{index}",
        webhook_url="http://localhost:9999/webhook",
        webhook_secret="launch-secret-32chars-minimum-ok",  # noqa: S106 - inert test HMAC secret
        services=["tree_removal"],
        target_zips=["32801"],
        exclusive_zips=[],
        bid_per_lead_t1_t2=Decimal("75.00"),
        bid_per_lead_t3=Decimal("150.00"),
        bid_per_call=Decimal("50.00"),
        filter_expression="true",
        daily_cap=10,
        monthly_budget=Decimal("1000.00"),
        deposit_balance=Decimal("1500.00"),
        low_balance_threshold=Decimal("100.00"),
        lifetime_spend=Decimal("0.00"),
    )


async def test_health_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ads_offline_conversion_export_is_dry_run_and_redacted(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORMLEAD_APPROVE_ADS_LIVE", raising=False)
    lead_id = uuid4()
    post_id = uuid4()
    lead = SimpleNamespace(
        id=lead_id,
        google_click_id="gclid-local-123",
        campaign_id="camp-1",
        campaign_source="google_ads",
        state="FL",
        zip="32801",
        requested_service="tree_removal",
        lead_class="a",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
        name="Jane Homeowner",
        phone_e164="+13215550123",
        email="jane@example.com",
        address_line1="100 Private St",
    )
    post = SimpleNamespace(
        id=post_id,
        bid_cents=45_000,
        created_at=datetime(2026, 5, 2, tzinfo=UTC),
    )
    older_duplicate_post = SimpleNamespace(
        id=uuid4(),
        bid_cents=30_000,
        created_at=datetime(2026, 5, 1, 12, tzinfo=UTC),
    )
    fake_session = FakeAdsSession(
        [(lead, older_duplicate_post), (lead, post)], wallet_runway_cents=150_000
    )
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/ads/offline-conversions",
        params={
            "market_zip": "32801",
            "service": "tree_removal",
            "campaign_id": "camp-1",
            "planned_spend_cents": 25_000,
            "campaign_budget_cents": 100_000,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "dry_run"
    assert body["would_contact_ads_provider"] is False
    assert body["would_upload"] is False
    assert body["provider_gate"]["live_upload"]["allowed"] is False
    assert body["export"]["format"] == "google_ads_offline_conversion_csv"
    assert body["export"]["pii_redacted"] is True
    assert body["export"]["excluded_fields"] == [
        "name",
        "phone_e164",
        "email",
        "address_line1",
    ]
    assert body["export"]["columns"] == api_module.ADS_OFFLINE_CONVERSION_COLUMNS
    assert body["export"]["row_count"] == 1
    row = body["export"]["rows"][0]
    assert row["Google Click ID"] == "gclid-local-123"
    assert row["Conversion Time"] == "2026-05-02 00:00:00+00:00"
    assert row["Conversion Value"] == "450.00"
    assert row["Order ID"] == f"lead:{lead_id}"
    assert row["redacted_context"]["post_result_id"] == str(post_id)
    assert body["export"]["csv_preview"].splitlines()[0] == ",".join(
        api_module.ADS_OFFLINE_CONVERSION_COLUMNS
    )
    assert "gclid-local-123" in body["export"]["csv_preview"]
    assert "Jane Homeowner" not in str(body)
    assert "+13215550123" not in str(body)
    assert "jane@example.com" not in str(body)
    assert "100 Private St" not in str(body)
    assert body["guardrails"]["decision"] == "dry_run_ready"
    assert "approval_required_before_live_ads_upload" in body["guardrails"]["recommended_actions"]


async def test_ads_offline_conversion_export_handles_empty_attribution(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_session = FakeAdsSession([], wallet_runway_cents=0)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/ads/offline-conversions",
        params={"planned_spend_cents": 50_000, "campaign_budget_cents": 25_000},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["export"]["row_count"] == 0
    assert body["guardrails"]["decision"] == "not_ready"
    assert "collect_attributed_sold_lead_evidence" in body["guardrails"]["recommended_actions"]
    assert "reduce_planned_spend_to_campaign_budget" in body["guardrails"]["recommended_actions"]
    assert "fund_buyer_wallets_before_spend" in body["guardrails"]["recommended_actions"]


async def test_ads_offline_conversion_requires_operator_token_when_enabled(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")

    response = await client.get("/v1/admin/ads/offline-conversions")

    assert response.status_code == 401
    assert response.json()["detail"] == "operator token required for admin or funding operations"


async def test_ads_offline_conversion_rejects_formula_conversion_name(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/v1/admin/ads/offline-conversions",
        params={"conversion_name": "=IMPORTDATA('https://example.invalid')"},
    )

    assert response.status_code == 400
    assert "conversion_name must start with a letter or number" in response.json()["detail"]


async def test_ads_endpoint_stays_dry_run_even_after_ads_approval(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_APPROVE_ADS_LIVE", "true")
    lead = SimpleNamespace(
        id=uuid4(),
        google_click_id="gclid-approved-123",
        campaign_id="camp-approved",
        campaign_source="google_ads",
        state="FL",
        zip="32801",
        requested_service="tree_removal",
        lead_class="a",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    post = SimpleNamespace(
        id=uuid4(),
        bid_cents=60_000,
        created_at=datetime(2026, 5, 2, tzinfo=UTC),
    )
    monkeypatch.setattr(api_module, "get_session", lambda: FakeAdsSession([(lead, post)], 200_000))

    response = await client.get(
        "/v1/admin/ads/offline-conversions",
        params={"planned_spend_cents": 25_000, "campaign_budget_cents": 100_000},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "dry_run"
    assert body["would_contact_ads_provider"] is False
    assert body["would_upload"] is False
    assert body["provider_gate"]["live_upload"]["allowed"] is True
    assert body["guardrails"]["decision"] == "live_upload_ready"


def test_ads_offline_conversion_rows_skip_blank_gclid() -> None:
    lead = SimpleNamespace(
        id=uuid4(),
        google_click_id="",
        campaign_id="camp-blank",
        campaign_source="google_ads",
        state="FL",
        zip="32801",
        requested_service="tree_removal",
        lead_class="a",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    post = SimpleNamespace(
        id=uuid4(), bid_cents=60_000, created_at=datetime(2026, 5, 2, tzinfo=UTC)
    )

    assert api_module._ads_offline_conversion_rows([(lead, post)], "Test Conversion") == []


def test_ads_offline_conversion_rows_skip_invalid_gclid_and_non_positive_bid() -> None:
    invalid_gclid_lead = SimpleNamespace(
        id=uuid4(),
        google_click_id="=SUM12345",
        campaign_id="camp-invalid",
        campaign_source="google_ads",
        state="FL",
        zip="32801",
        requested_service="tree_removal",
        lead_class="a",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    zero_bid_lead = SimpleNamespace(
        id=uuid4(),
        google_click_id="gclid-valid-123",
        campaign_id="camp-zero",
        campaign_source="google_ads",
        state="FL",
        zip="32801",
        requested_service="tree_removal",
        lead_class="a",
        created_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    invalid_post = SimpleNamespace(
        id=uuid4(), bid_cents=60_000, created_at=datetime(2026, 5, 2, tzinfo=UTC)
    )
    zero_bid_post = SimpleNamespace(
        id=uuid4(), bid_cents=0, created_at=datetime(2026, 5, 2, tzinfo=UTC)
    )

    assert (
        api_module._ads_offline_conversion_rows(
            [(invalid_gclid_lead, invalid_post), (zero_bid_lead, zero_bid_post)],
            "Test Conversion",
        )
        == []
    )


def test_ads_conversion_time_formats_offset_as_google_ads_utc() -> None:
    eastern_time = datetime(2026, 5, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-4)))

    assert api_module._format_ads_conversion_time(eastern_time) == "2026-05-02 07:04:05+00:00"


def test_ads_guardrail_preview_isolates_spend_value_and_wallet_failures() -> None:
    poor_value = api_module._ads_spend_guardrail_preview(
        row_count=1,
        attributed_conversion_value_cents=10_000,
        campaign_budget_cents=100_000,
        planned_spend_cents=50_000,
        wallet_runway_cents=150_000,
        live_ads_approved=False,
    )
    poor_wallet = api_module._ads_spend_guardrail_preview(
        row_count=1,
        attributed_conversion_value_cents=120_000,
        campaign_budget_cents=100_000,
        planned_spend_cents=50_000,
        wallet_runway_cents=25_000,
        live_ads_approved=False,
    )

    assert "review_unit_economics_before_spend" in poor_value["recommended_actions"]
    assert "fund_buyer_wallets_before_spend" not in poor_value["recommended_actions"]
    assert "fund_buyer_wallets_before_spend" in poor_wallet["recommended_actions"]
    assert "review_unit_economics_before_spend" not in poor_wallet["recommended_actions"]


def test_ads_guardrail_preview_allows_live_only_after_approval() -> None:
    blocked = api_module._ads_spend_guardrail_preview(
        row_count=1,
        attributed_conversion_value_cents=120_000,
        campaign_budget_cents=100_000,
        planned_spend_cents=50_000,
        wallet_runway_cents=150_000,
        live_ads_approved=False,
    )
    approved = api_module._ads_spend_guardrail_preview(
        row_count=1,
        attributed_conversion_value_cents=120_000,
        campaign_budget_cents=100_000,
        planned_spend_cents=50_000,
        wallet_runway_cents=150_000,
        live_ads_approved=True,
    )

    assert blocked["decision"] == "dry_run_ready"
    assert blocked["live_upload_ready"] is False
    assert approved["decision"] == "live_upload_ready"
    assert approved["live_upload_ready"] is True


async def test_launch_readiness_stays_technical_without_commercial_approval(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE", raising=False)
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)
    fake_session = FakeLaunchReadinessSession(
        scalar_values=[3, 3, 300_000, 3, 1, 1, 1, 1, 1],
        buyers=[_launch_ready_buyer(index) for index in range(3)],
    )
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/launch-readiness",
        params={
            "market_zip": "32801",
            "service": "tree_removal",
            "campaign_budget_cents": 100_000,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["local_simulation_ready"] is True
    assert body["technical_local_ready"] is True
    assert body["commercial_paid_launch_ready"] is False
    assert body["ready_for_paid_launch"] is False
    assert body["readiness_label"] == "technical_local_ready"
    assert body["checks"]["buyer_delivery_live_approval_present"] is False
    assert body["checks"]["live_payment_approval_present"] is False
    assert body["metrics"]["funded_buyers"] == 3
    assert body["buyer_activation_funnel"]["autopilot_ready_buyers"] == 3


async def test_launch_readiness_requires_three_funded_wallet_ready_buyers(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", "true")
    fake_session = FakeLaunchReadinessSession(
        scalar_values=[2, 2, 90_000, 2, 1, 1, 1, 1, 1],
        buyers=[_launch_ready_buyer(index) for index in range(2)],
    )
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/launch-readiness",
        params={
            "market_zip": "32801",
            "service": "tree_removal",
            "campaign_budget_cents": 100_000,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["local_simulation_ready"] is True
    assert body["technical_local_ready"] is False
    assert body["commercial_paid_launch_ready"] is False
    assert body["ready_for_paid_launch"] is False
    assert body["readiness_label"] == "local_simulation_ready"
    assert body["checks"]["buyer_delivery_live_approval_present"] is True
    assert body["checks"]["live_payment_approval_present"] is True
    assert body["checks"]["three_funded_buyers_in_scope"] is False
    assert body["checks"]["buyers_have_services_zips_caps_and_prices"] is False
    assert body["checks"]["buyers_are_activation_ready"] is False
    assert body["checks"]["wallet_balance_covers_campaign_budget"] is False
    assert body["checks"]["buyer_wallet_runway_covers_pause_threshold"] is False


async def test_launch_readiness_requires_scoped_call_tracking_evidence(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", "true")
    fake_session = FakeLaunchReadinessSession(
        scalar_values=[3, 3, 300_000, 3, 1, 1, 1, 1, 0],
        buyers=[_launch_ready_buyer(index) for index in range(3)],
    )
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/launch-readiness",
        params={
            "market_zip": "32801",
            "service": "tree_removal",
            "campaign_budget_cents": 100_000,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["local_simulation_ready"] is False
    assert body["technical_local_ready"] is False
    assert body["commercial_paid_launch_ready"] is False
    assert body["ready_for_paid_launch"] is False
    assert body["readiness_label"] == "not_ready"
    assert body["checks"]["synthetic_call_tracking_ingested"] is False
    assert body["checks"]["call_tracking_ingested"] is False
    assert body["checks"]["buyer_delivery_live_approval_present"] is True
    assert body["checks"]["live_payment_approval_present"] is True
    assert body["metrics"]["matched_call_events"] == 0


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


async def test_admin_buyer_webhook_default_uses_local_env(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_LOCAL_BUYER_WEBHOOK_BASE", "http://localhost:61234")

    response = await client.get("/admin")

    assert response.status_code == 200
    assert 'value="http://localhost:61234/cowork-buyer"' in response.text
    assert "host.docker.internal:9999/cowork-buyer" not in response.text


async def test_admin_dashboard_includes_durable_exception_summary(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/admin")

    assert response.status_code == 200
    assert 'id="exception-summary"' in response.text
    assert 'id="exception-summary-label"' in response.text
    assert "Durable Queue Summary" in response.text
    assert "/v1/admin/autopilot/exception-queue/summary" in response.text
    assert "Aggregates only; no homeowner PII" in response.text
    assert 'id="budget-actions-summary"' in response.text
    assert 'id="budget-actions-label"' in response.text
    assert 'id="budget-actions"' in response.text
    assert "Budget Action Queue" in response.text
    assert "/v1/admin/autopilot/budget-actions/summary" in response.text
    assert "No ad platform mutation or spend" in response.text
    assert 'id="learning-proposals-summary"' in response.text
    assert 'id="learning-proposals-label"' in response.text
    assert 'id="learning-proposals"' in response.text
    assert "Learning Proposal Queue" in response.text
    assert "/v1/admin/autopilot/learning-proposals/summary" in response.text
    assert "No live traffic routing or automatic promotion" in response.text


async def test_create_buyer_rejects_external_webhook_before_commercial_approval(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", raising=False)

    response = await client.post(
        "/v1/buyers",
        json=_buyer_create_payload("https://buyer.example.com/webhook"),
    )

    assert response.status_code == 422
    assert "buyer webhook_url must stay local" in response.text


def test_buyer_create_request_allows_external_webhook_after_commercial_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.example.com")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )

    payload = api_module.BuyerCreateRequest.model_validate(
        _buyer_create_payload("https://buyer.example.com/webhook")
    )

    assert payload.webhook_url == "https://buyer.example.com/webhook"


def test_buyer_create_request_rejects_approved_external_webhook_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.setenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", "buyer.example.com")
    monkeypatch.setattr(
        "stormlead_core.env_gate.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("10.0.0.5", 443))],
    )

    with pytest.raises(ValueError, match="approved HTTPS buyer host"):
        api_module.BuyerCreateRequest.model_validate(
            _buyer_create_payload("https://buyer.example.com/webhook")
        )


def test_buyer_create_request_rejects_unapproved_external_webhook_after_launch_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "true")
    monkeypatch.delenv("STORMLEAD_APPROVED_BUYER_WEBHOOK_HOSTS", raising=False)

    with pytest.raises(ValueError, match="approved HTTPS buyer host"):
        api_module.BuyerCreateRequest.model_validate(
            _buyer_create_payload("https://buyer.example.com/webhook")
        )


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


async def test_local_refill_intent_returns_synthetic_contract(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.post(
        f"/v1/buyers/{buyer_id}/wallet/refill-intents",
        json={"amount_cents": 50000, "idempotency_key": "local-refill-test"},
        headers={"Authorization": "Bearer test-operator-token"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "local"
    assert body["provider_gate"]["allowed"] is True
    assert body["live_payment_approval"]["required"] is True
    assert body["checkout_contract"]["live_checkout_url"] is None
    assert body["checkout_contract"]["would_contact_payment_provider"] is False
    assert body["checkout_contract"]["webhook_endpoint"] == "/v1/payments/refill-events"
    assert body["checkout_contract"]["event_payload"]["buyer_id"] == str(buyer_id)
    assert "Stripe Checkout" in body["checkout_contract"]["operator_steps"][-1]
    assert str(buyer_id) in body["idempotency_key"]
    assert "local-refill-test" in body["idempotency_key"]


async def test_stripe_refill_intent_requires_payment_approval(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.post(
        f"/v1/buyers/{buyer_id}/wallet/refill-intents",
        json={"amount_cents": 50000, "provider": "stripe"},
        headers={"Authorization": "Bearer test-operator-token"},
    )

    body = response.json()
    assert response.status_code == 403
    assert body["detail"]["provider_gate"]["allowed"] is False
    assert body["detail"]["approval_packet"]["status"] == "approval_required"


async def test_local_refill_event_credits_wallet_once(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)
    payload = {
        "provider": "local",
        "provider_event_id": "evt_local_refill_1",
        "payment_intent_id": "local_pi_refill_1",
        "buyer_id": str(buyer_id),
        "amount_cents": 62500,
        "currency": "USD",
        "status": "succeeded",
        "idempotency_key": "local-refill-event-key",
        "metadata": {
            "card_token": "do-not-store",
            "description": "client_secret=pi_test_secret_123",
            "note": "pilot refill",
            "webhook_note": "whsec_test_123",
        },
    }

    first = await client.post(
        "/v1/payments/refill-events",
        json=payload,
        headers={"Authorization": "Bearer test-operator-token"},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["status"] == "credited"
    assert first_body["external_event_id"] == "evt_local_refill_1"
    assert first_body["payment_webhook_event_status"] == "processed"
    assert first_body["buyer"]["deposit_balance_cents"] == 62500
    assert (
        sum("pg_advisory_xact_lock" in statement for statement in fake_session.executed_statements)
        == 3
    )
    assert fake_session.get_kwargs[0]["with_for_update"] is True
    assert len(fake_session.added) == 2
    webhook_event = fake_session.added[0]
    assert isinstance(webhook_event, api_module.PaymentWebhookEvent)
    assert first_body["payment_webhook_event_id"] == str(webhook_event.id)
    assert webhook_event.provider == "local"
    assert webhook_event.external_event_id == "evt_local_refill_1"
    assert webhook_event.event_type == "wallet.refill.succeeded"
    assert webhook_event.status == "processed"
    assert len(webhook_event.payload_sha256) == 64
    assert webhook_event.payload_json["metadata"]["card_token"] == "[redacted]"  # noqa: S105
    assert webhook_event.payload_json["metadata"]["description"] == "[redacted]"
    assert webhook_event.payload_json["metadata"]["webhook_note"] == "[redacted]"
    assert webhook_event.payload_json["metadata"]["note"] == "pilot refill"
    event = fake_session.added[1]
    assert isinstance(event, api_module.BillingEvent)
    assert event.external_event_id == "evt_local_refill_1"
    metadata = event.metadata_json
    assert metadata["payment_event_id"] == "evt_local_refill_1"
    assert metadata["payment_webhook_event_id"] == str(webhook_event.id)
    assert metadata["metadata"]["card_token"] == "[redacted]"  # noqa: S105
    assert metadata["metadata"]["description"] == "[redacted]"
    assert metadata["metadata"]["webhook_note"] == "[redacted]"
    assert metadata["metadata"]["note"] == "pilot refill"

    fake_session.existing_payment_event = event
    same_intent_replay = await client.post(
        "/v1/payments/refill-events",
        json={**payload, "provider_event_id": "evt_local_refill_1_retry"},
        headers={"Authorization": "Bearer test-operator-token"},
    )

    duplicate_body = same_intent_replay.json()
    assert same_intent_replay.status_code == 200
    assert duplicate_body["idempotent_replay"] is True
    assert duplicate_body["status"] == "duplicate_ignored"
    assert duplicate_body["external_event_id"] == "evt_local_refill_1"
    ignored_webhook_event = fake_session.added[2]
    assert isinstance(ignored_webhook_event, api_module.PaymentWebhookEvent)
    assert ignored_webhook_event.external_event_id == "evt_local_refill_1_retry"
    assert ignored_webhook_event.status == "ignored"
    assert duplicate_body["payment_webhook_event_id"] == str(ignored_webhook_event.id)
    assert duplicate_body["payment_webhook_event_status"] == "ignored"
    assert duplicate_body["buyer"]["deposit_balance_cents"] == 62500
    assert len(fake_session.added) == 3

    conflict = await client.post(
        "/v1/payments/refill-events",
        json={
            **payload,
            "provider_event_id": "evt_local_refill_conflict",
            "amount_cents": 70000,
        },
        headers={"Authorization": "Bearer test-operator-token"},
    )

    assert conflict.status_code == 409
    assert "idempotency conflict" in conflict.json()["detail"]
    assert fake_session.exit_exc_types[-1] is None
    assert duplicate_body["buyer"]["deposit_balance_cents"] == 62500
    failed_webhook_event = fake_session.added[3]
    assert isinstance(failed_webhook_event, api_module.PaymentWebhookEvent)
    assert failed_webhook_event.external_event_id == "evt_local_refill_conflict"
    assert failed_webhook_event.status == "failed"
    assert len(fake_session.added) == 4


async def test_refill_event_rejects_failed_or_unapproved_live_events(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)
    base_payload = {
        "provider_event_id": "evt_local_refill_failed",
        "payment_intent_id": "local_pi_refill_failed",
        "buyer_id": str(buyer_id),
        "amount_cents": 62500,
        "currency": "USD",
    }

    failed = await client.post(
        "/v1/payments/refill-events",
        json={**base_payload, "provider": "local", "status": "failed"},
        headers={"Authorization": "Bearer test-operator-token"},
    )
    assert failed.status_code == 409
    assert fake_session.buyer.deposit_balance == Decimal("0.00")

    live = await client.post(
        "/v1/payments/refill-events",
        json={**base_payload, "provider": "stripe", "status": "succeeded"},
        headers={"Authorization": "Bearer test-operator-token"},
    )
    assert live.status_code == 403
    assert fake_session.buyer.deposit_balance == Decimal("0.00")


async def test_approved_live_refill_event_still_requires_signed_provider_webhook(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", "true")

    buyer_id = uuid4()
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, f"buyer-{buyer_id.hex}"))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.post(
        "/v1/payments/refill-events",
        json={
            "provider": "stripe",
            "provider_event_id": "evt_stripe_refill_1",
            "payment_intent_id": "pi_stripe_refill_1",
            "buyer_id": str(buyer_id),
            "amount_cents": 62500,
            "currency": "USD",
            "status": "succeeded",
        },
        headers={"Authorization": "Bearer test-operator-token"},
    )

    assert response.status_code == 403
    assert "signed Stripe webhook" in response.json()["detail"]["message"]
    assert fake_session.buyer.deposit_balance == Decimal("0.00")


async def test_wallet_reconciliation_endpoint_requires_buyer_key_and_returns_ledger(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)

    buyer_id = uuid4()
    buyer_key = f"buyer-{buyer_id.hex}"
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, buyer_key))
    fake_session.buyer.deposit_balance = Decimal("300.00")
    fake_session.scalar_value = 30000
    reconciliation_event = api_module.BillingEvent(
        id=uuid4(),
        buyer_id=buyer_id,
        lead_id=None,
        event_type="deposit.added",
        amount_cents=30000,
        metadata_json={
            "source": "payment_refill_event",
            "payment_provider": "local",
            "payment_event_id": "evt_reconcile_endpoint",
            "payment_intent_id": "local_pi_reconcile_endpoint",
        },
    )
    reconciliation_event.created_at = datetime.now(UTC)
    fake_session.existing_payment_event = reconciliation_event
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    missing = await client.get(f"/v1/buyers/{buyer_id}/wallet/reconciliation")
    assert missing.status_code == 401

    response = await client.get(
        f"/v1/buyers/{buyer_id}/wallet/reconciliation",
        headers={"Authorization": f"Bearer {buyer_key}"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["ledger"]["reconciled"] is True
    assert body["ledger"]["recent_funding_events"][0]["payment_event_id"] == (
        "evt_reconcile_endpoint"
    )
    assert body["ledger"]["recent_funding_events"][0]["external_event_id"] is None
    assert body["payment_readiness"]["live_payments_approved"] is False


def test_wallet_reconciliation_payload_exposes_delta_and_payment_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STORMLEAD_APPROVE_PAYMENTS_LIVE", raising=False)
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.deposit_balance = Decimal("500.00")
    event = api_module.BillingEvent(
        id=uuid4(),
        buyer_id=buyer_id,
        lead_id=None,
        event_type="deposit.added",
        amount_cents=30000,
        metadata_json={
            "source": "payment_refill_event",
            "payment_provider": "local",
            "payment_event_id": "evt_reconcile",
            "payment_intent_id": "local_pi_reconcile",
        },
    )
    event.created_at = datetime.now(UTC)

    payload = api_module._wallet_reconciliation_payload(
        buyer, ledger_total_cents=30000, recent_funding_events=[event]
    )

    assert payload["ledger"]["mutable_balance_cents"] == 50000
    assert payload["ledger"]["signed_total_cents"] == 30000
    assert payload["ledger"]["delta_cents"] == 20000
    assert payload["ledger"]["reconciled"] is False
    assert payload["payment_readiness"]["local_refills_ready"] is True
    assert payload["payment_readiness"]["live_payments_approved"] is False


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


async def test_buyer_can_rotate_api_key_and_old_key_stops_working(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")

    buyer_id = uuid4()
    old_key = f"buyer-{buyer_id.hex}"
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, old_key))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    missing = await client.post(f"/v1/buyers/{buyer_id}/api-key/rotate")
    assert missing.status_code == 401

    rotated = await client.post(
        f"/v1/buyers/{buyer_id}/api-key/rotate",
        headers={"Authorization": f"Bearer {old_key}"},
    )
    body = rotated.json()
    assert rotated.status_code == 200
    assert rotated.headers["cache-control"] == "no-store, private"
    assert rotated.headers["pragma"] == "no-cache"
    assert body["api_key"].startswith("buyer_")
    assert body["api_key"] != old_key
    assert fake_session.buyer.api_key == body["api_key"]

    old_wallet = await client.get(
        f"/v1/buyers/{buyer_id}/wallet",
        headers={"Authorization": f"Bearer {old_key}"},
    )
    assert old_wallet.status_code == 401

    new_wallet = await client.get(
        f"/v1/buyers/{buyer_id}/wallet",
        headers={"Authorization": f"Bearer {body['api_key']}"},
    )
    assert new_wallet.status_code == 200


async def test_operator_can_rotate_buyer_api_key_with_operator_token(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")

    buyer_id = uuid4()
    old_key = f"buyer-{buyer_id.hex}"
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, old_key))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    rotated = await client.post(
        f"/v1/buyers/{buyer_id}/api-key/rotate",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert rotated.status_code == 200
    assert rotated.json()["api_key"] != old_key


async def test_api_key_rotation_does_not_accept_local_operator_bypass_token(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_BUYER_API_KEY", "true")
    monkeypatch.delenv("STORMLEAD_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", raising=False)

    buyer_id = uuid4()
    old_key = f"buyer-{buyer_id.hex}"
    fake_session = FakeBuyerSession(_test_buyer(buyer_id, old_key))
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    rotated = await client.post(
        f"/v1/buyers/{buyer_id}/api-key/rotate",
        headers={"x-stormlead-operator-token": "anything-local"},
    )

    assert rotated.status_code == 401
    assert fake_session.buyer.api_key == old_key


async def test_admin_provider_kill_switches_is_read_only_local_status(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("STORMLEAD_PAUSE_SMS", "true")
    monkeypatch.delenv("STORMLEAD_PAUSE_EMAIL", raising=False)

    response = await client.get(
        "/v1/admin/provider-kill-switches",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["would_contact_provider"] is False
    assert body["safe_to_call_without_provider_credentials"] is True
    assert body["kill_switches"]["sms"]["paused"] is True
    assert body["kill_switches"]["sms"]["pause_env"] == "STORMLEAD_PAUSE_SMS"
    assert body["kill_switches"]["email"]["paused"] is False
    assert body["paused_areas"] == ["sms"]
    assert body["change_plan_endpoint"] == "/v1/admin/provider-kill-switches/change-plan"


async def test_admin_provider_kill_switch_change_plan_is_approval_safe(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.delenv("STORMLEAD_PAUSE_SMS", raising=False)

    response = await client.post(
        "/v1/admin/provider-kill-switches/change-plan",
        headers={"x-stormlead-operator-token": "test-operator-token"},
        json={
            "area": "sms",
            "desired_paused": True,
            "reason": "delivery provider incident",
        },
    )

    assert response.status_code == 200
    body = response.json()
    plan = body["plan"]
    assert body["mode"] == "local_provider_kill_switch_change_plan"
    assert body["would_contact_provider"] is False
    assert body["would_mutate_runtime"] is False
    assert body["safe_to_call_without_provider_credentials"] is True
    assert body["current_snapshot"]["paused"] is False
    assert plan["area"] == "sms"
    assert plan["action"] == "pause"
    assert plan["approval_required"] is True
    assert plan["would_change"] is True
    assert plan["required_config"] == {"STORMLEAD_PAUSE_SMS": "true"}
    assert plan["rollback_config"] == {"STORMLEAD_PAUSE_SMS": "false"}
    assert plan["would_contact_provider"] is False
    assert plan["would_mutate_runtime"] is False
    assert os.getenv("STORMLEAD_PAUSE_SMS") is None


def test_buyer_timeout_cluster_exception_materializes_owner_and_sla() -> None:
    buyer_id = uuid4()
    now = datetime(2026, 5, 13, 15, 0, tzinfo=UTC)

    def failed_post(
        created_at: datetime, *, status_code: int | None = None
    ) -> api_module.PostResult:
        return api_module.PostResult(
            id=uuid4(),
            lead_id=uuid4(),
            buyer_id=buyer_id,
            bid_cents=7_500,
            delivered=False,
            response_status_code=status_code,
            response_body="timeout waiting for buyer" if status_code is None else "server error",
            created_at=created_at,
        )

    posts = [
        failed_post(now - timedelta(minutes=45)),
        failed_post(now - timedelta(minutes=30)),
        failed_post(now - timedelta(minutes=5)),
        failed_post(now - timedelta(hours=3)),
        failed_post(now - timedelta(minutes=4), status_code=500),
    ]

    items = api_module._buyer_timeout_cluster_exception_items(posts, now=now)

    assert len(items) == 1
    item = items[0]
    assert item["exception_id"] == f"buyer:{buyer_id}:timeout_cluster"
    assert item["kind"] == "buyer_timeout_cluster"
    assert item["severity"] == "critical"
    assert item["entity_type"] == "buyer"
    assert item["buyer_id"] == str(buyer_id)
    assert item["lead_id"] is None
    assert "3 timeout-like post failures" in item["recommended_action"]

    queue_row = api_module._new_exception_queue_item(item, now=now)
    assert queue_row.owner == "ops-oncall"
    assert queue_row.sla_due_at == now - timedelta(minutes=45) + timedelta(hours=1)
    assert queue_row.idempotency_key == f"buyer:{buyer_id}:timeout_cluster"
    assert queue_row.payload_json["source"] == "computed_admin_autopilot_exceptions"


async def test_exception_queue_sync_inserts_and_refreshes_idempotently() -> None:
    lead_id = uuid4()
    buyer_id = uuid4()
    post_id = uuid4()
    created_at = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
    sync_now = datetime(2026, 5, 13, 12, 30, tzinfo=UTC)
    existing = api_module.ExceptionQueueItem(
        kind="delivery_failure",
        severity="warning",
        status="open",
        owner="ops-oncall",
        entity_type="post_result",
        lead_id=lead_id,
        buyer_id=buyer_id,
        post_result_id=post_id,
        reason="old_reason",
        recommended_action="Old action",
        idempotency_key=f"post:{post_id}:delivery",
        sla_due_at=created_at + timedelta(hours=24),
        payload_json={},
    )
    fake_session = FakeExceptionQueueSession([[], [existing]])
    items = [
        {
            "exception_id": f"lead:{lead_id}:review",
            "kind": "lead_review",
            "severity": "critical",
            "reason": "human_review_required",
            "entity_type": "lead",
            "lead_id": str(lead_id),
            "buyer_id": None,
            "return_request_id": None,
            "post_result_id": None,
            "market": "FL-32801",
            "service": "tree_removal",
            "created_at": created_at.isoformat(),
            "sla_age_minutes": 30,
            "recommended_action": "Open the timeline and approve only with policy evidence.",
            "actions": ["open_timeline", "approve_lead"],
        },
        {
            "exception_id": f"post:{post_id}:delivery",
            "kind": "delivery_failure",
            "severity": "critical",
            "reason": "post_failed",
            "entity_type": "post_result",
            "lead_id": str(lead_id),
            "buyer_id": str(buyer_id),
            "return_request_id": None,
            "post_result_id": str(post_id),
            "market": "FL-32801",
            "service": "tree_removal",
            "created_at": created_at.isoformat(),
            "sla_age_minutes": 30,
            "recommended_action": "Check buyer webhook health before rerouting.",
            "actions": ["open_timeline"],
        },
    ]

    summary = await api_module._sync_exception_queue_items(fake_session, items, now=sync_now)

    assert summary == {"inserted": 1, "updated": 1, "skipped_closed": 0, "computed": 2}
    assert fake_session.flushed is True
    inserted = fake_session.added[0]
    assert inserted.idempotency_key == f"lead:{lead_id}:review"
    assert inserted.owner == "review-ops"
    assert inserted.sla_due_at == created_at + timedelta(hours=1)
    assert inserted.payload_json["source"] == "computed_admin_autopilot_exceptions"
    assert inserted.payload_json["actions"] == ["open_timeline", "approve_lead"]
    assert existing.reason == "post_failed"
    assert existing.severity == "critical"
    assert existing.sla_due_at == created_at + timedelta(hours=1)
    assert existing.payload_json["source_exception_id"] == f"post:{post_id}:delivery"


async def test_admin_exception_sync_endpoint_is_local_and_operator_gated(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    fake_session = FakeEmptySession()
    item = {
        "exception_id": "buyer:local:onboarding",
        "kind": "buyer_onboarding_incomplete",
        "severity": "info",
        "reason": "buyer_not_autopilot_ready",
        "entity_type": "buyer",
        "created_at": datetime(2026, 5, 13, tzinfo=UTC).isoformat(),
        "sla_age_minutes": 0,
        "recommended_action": "Complete local buyer readiness checks.",
        "actions": [],
    }
    captured: dict[str, object] = {}

    async def fake_build(*args: object, **kwargs: object) -> list[dict[str, object]]:
        captured["build_args"] = args
        captured["build_kwargs"] = kwargs
        return [item]

    async def fake_sync(*args: object, **kwargs: object) -> dict[str, int]:
        captured["sync_args"] = args
        captured["sync_kwargs"] = kwargs
        return {"inserted": 1, "updated": 0, "skipped_closed": 0, "computed": 1}

    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)
    monkeypatch.setattr(api_module, "_build_autopilot_exceptions", fake_build)
    monkeypatch.setattr(api_module, "_sync_exception_queue_items", fake_sync)

    response = await client.post(
        "/v1/admin/autopilot/exceptions/sync?limit=25",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_exception_queue_sync"
    assert body["would_contact_provider"] is False
    assert body["computed_count"] == 1
    assert body["sync"]["inserted"] == 1
    assert captured["build_args"] == (fake_session,)
    assert captured["build_kwargs"] == {
        "limit": 25,
        "kind": None,
        "lead_id": None,
        "buyer_id": None,
    }
    assert captured["sync_args"] == (fake_session, [item])


async def test_exception_queue_summary_groups_active_rows_without_pii(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    lead_id = uuid4()
    buyer_id = uuid4()
    past_sla = datetime.now(UTC) - timedelta(minutes=5)
    future_sla = datetime.now(UTC) + timedelta(hours=2)
    rows = [
        api_module.ExceptionQueueItem(
            kind="delivery_failure",
            severity="critical",
            status="open",
            owner="ops-oncall",
            entity_type="post_result",
            lead_id=lead_id,
            buyer_id=buyer_id,
            reason="post_failed",
            recommended_action="Check buyer webhook health.",
            idempotency_key="post:local:delivery",
            sla_due_at=past_sla,
            payload_json={"lead_id": str(lead_id)},
        ),
        api_module.ExceptionQueueItem(
            kind="buyer_wallet_low",
            severity="warning",
            status="in_progress",
            owner="buyer-success",
            entity_type="buyer",
            buyer_id=buyer_id,
            reason="wallet_below_threshold",
            recommended_action="Collect or simulate wallet funding.",
            idempotency_key="buyer:local:wallet",
            sla_due_at=future_sla,
            payload_json={"buyer_id": str(buyer_id)},
        ),
        api_module.ExceptionQueueItem(
            kind="return_pending",
            severity="info",
            status="resolved",
            owner="support-ops",
            entity_type="return_request",
            reason="duplicate",
            recommended_action="Already handled.",
            idempotency_key="return:local",
            sla_due_at=past_sla,
            payload_json={},
        ),
    ]
    fake_session = FakeExceptionQueueSession([rows])
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/autopilot/exception-queue/summary",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_read_only"
    assert body["would_contact_provider"] is False
    assert body["pii_redacted"] is True
    assert body["active_count"] == 2
    assert body["overdue_count"] == 1
    assert body["by_status"] == {"open": 1, "in_progress": 1}
    assert body["by_severity"] == {"critical": 1, "warning": 1}
    assert body["by_owner"] == {"ops-oncall": 1, "buyer-success": 1}
    assert body["by_kind"] == {"delivery_failure": 1, "buyer_wallet_low": 1}
    assert body["by_area"] == {"auction": 1, "finance": 1}
    assert str(lead_id) not in str(body)
    assert str(buyer_id) not in str(body)


async def test_budget_action_summary_is_read_only_approval_queue(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    campaign_id = uuid4()
    created_at = datetime(2026, 5, 13, 13, 0, tzinfo=UTC)
    rows = [
        api_module.BudgetActionLog(
            campaign_id=campaign_id,
            platform="google_ads",
            external_campaign_id="campaign-approval",
            action="propose_increase",
            status="approval_required",
            approval_required=True,
            reason="budget_increase_requires_admin_approval",
            idempotency_key="budget-pacing:propose_increase:approval",
            metrics_json={
                "current_daily_budget_cents": 10_000,
                "proposed_daily_budget_cents": 12_500,
                "spend_cents": 4_000,
            },
            decision_json={
                "evaluation_date": "2026-05-13",
                "max_daily_budget_cents": 25_000,
                "would_contact_ads_provider": False,
                "would_mutate_ads_provider": False,
                "would_spend_money": False,
                "approval_required_before_live_ads_action": True,
            },
            created_at=created_at,
        ),
        api_module.BudgetActionLog(
            campaign_id=campaign_id,
            platform="meta",
            external_campaign_id="campaign-blocked",
            action="block_increase",
            status="blocked",
            approval_required=False,
            reason="proposed_daily_budget_exceeds_cap",
            idempotency_key="budget-pacing:block_increase:blocked",
            metrics_json={"proposed_daily_budget_cents": 50_000, "spend_cents": 2_000},
            decision_json={
                "evaluation_date": "2026-05-13",
                "would_contact_ads_provider": False,
                "would_mutate_ads_provider": True,
                "would_spend_money": True,
            },
            created_at=created_at - timedelta(minutes=5),
        ),
        api_module.BudgetActionLog(
            campaign_id=campaign_id,
            platform="meta",
            external_campaign_id="campaign-lossy",
            action="auto_pause",
            status="planned",
            approval_required=False,
            reason="loss_threshold_exceeded",
            idempotency_key="budget-pacing:auto_pause:lossy",
            metrics_json={"spend_cents": 20_000, "qualified_leads": 1, "cpl_cents": 20_000},
            decision_json={
                "evaluation_date": "2026-05-13",
                "would_contact_ads_provider": False,
                "would_mutate_ads_provider": False,
                "would_spend_money": False,
            },
            created_at=created_at - timedelta(minutes=10),
        ),
        api_module.BudgetActionLog(
            campaign_id=campaign_id,
            platform="google_ads",
            external_campaign_id="campaign-held",
            action="hold",
            status="skipped",
            approval_required=False,
            reason="within_budget_pacing_policy",
            idempotency_key="budget-pacing:hold:skipped",
            metrics_json={},
            decision_json={},
            created_at=created_at - timedelta(minutes=20),
        ),
    ]
    fake_session = FakeBudgetActionSession(rows)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/autopilot/budget-actions/summary?limit=2",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_read_only"
    assert body["source"] == "budget_action_logs"
    assert body["endpoint_would_contact_ads_provider"] is False
    assert body["endpoint_would_mutate_ads_provider"] is False
    assert body["endpoint_would_spend_money"] is False
    assert body["rows_with_provider_contact_intent"] == 0
    assert body["rows_with_provider_mutation_intent"] == 1
    assert body["rows_with_spend_intent"] == 1
    assert body["active_count"] == 3
    assert body["approval_required_count"] == 1
    assert body["auto_pause_count"] == 1
    assert body["blocked_count"] == 1
    assert body["by_action"] == {
        "propose_increase": 1,
        "block_increase": 1,
        "auto_pause": 1,
    }
    assert body["by_status"] == {"approval_required": 1, "blocked": 1, "planned": 1}
    assert body["by_platform"] == {"google_ads": 1, "meta": 2}
    assert len(body["recent_actions"]) == 2
    proposal = body["recent_actions"][0]
    assert proposal["action"] == "propose_increase"
    assert proposal["approval_required"] is True
    assert proposal["metrics"]["proposed_daily_budget_cents"] == 12_500
    assert proposal["decision"]["would_spend_money"] is False
    assert proposal["safety"] == {
        "would_contact_ads_provider": False,
        "would_mutate_ads_provider": False,
        "would_spend_money": False,
    }
    blocked = body["recent_actions"][1]
    assert blocked["action"] == "block_increase"
    assert blocked["safety"]["would_mutate_ads_provider"] is True
    assert blocked["safety"]["would_spend_money"] is True


async def test_learning_proposal_summary_is_read_only_admin_queue(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORMLEAD_REQUIRE_OPERATOR_TOKEN", "true")
    monkeypatch.setenv("STORMLEAD_OPERATOR_TOKEN", "test-operator-token")
    created_at = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)
    proposal_date = created_at.date()
    rows = [
        api_module.LearningProposal(
            proposal_date=proposal_date,
            proposal_type="scoring_threshold",
            target_area="qualification",
            title="Raise storm damage confidence threshold",
            rationale="Replay improved conversion quality.",
            status="pending_approval",
            canary_percent=5,
            approval_required=True,
            guardrail_metric="conversion_rate",
            baseline_value=0.60,
            candidate_value=0.63,
            rollback_threshold_pct=5.0,
            idempotency_key="learning:threshold:approval",
            proposal_json={
                "confidence": 0.82,
                "target_area": "qualification",
                "sensitive_context": "homeowner@example.com",
            },
            replay_result_json={
                "status": "pending_approval",
                "canary_percent": 5,
                "approval_required": True,
                "rollback_required": False,
                "reason": "100% promotion requires explicit admin approval.",
                "guardrail_metric": "conversion_rate",
                "baseline_rate": 0.60,
                "candidate_rate": 0.63,
                "relative_drop_pct": 0.0,
            },
            created_at=created_at,
            updated_at=created_at,
        ),
        api_module.LearningProposal(
            proposal_date=proposal_date,
            proposal_type="prompt_update",
            target_area="qualification_prompt",
            title="Reject low-intent claims earlier",
            status="rollback_triggered",
            canary_percent=0,
            approval_required=False,
            guardrail_metric="conversion_rate",
            baseline_value=0.60,
            candidate_value=0.50,
            rollback_threshold_pct=5.0,
            idempotency_key="learning:prompt:rollback",
            proposal_json={"confidence": 0.71, "private_trace": "+13215550123"},
            replay_result_json={
                "status": "rollback_triggered",
                "canary_percent": 0,
                "approval_required": False,
                "rollback_required": True,
                "relative_drop_pct": 16.6,
            },
            rollback_reason="Candidate conversion rate regressed beyond threshold.",
            created_at=created_at - timedelta(minutes=5),
            updated_at=created_at - timedelta(minutes=5),
        ),
        api_module.LearningProposal(
            proposal_date=proposal_date,
            proposal_type="cadence_change",
            target_area="follow_up_cadence",
            title="Delay second follow-up attempt",
            status="pending_replay",
            canary_percent=0,
            approval_required=True,
            guardrail_metric="contact_rate",
            idempotency_key="learning:cadence:pending",
            proposal_json={"confidence": 0.65},
            replay_result_json={},
            created_at=created_at - timedelta(minutes=10),
            updated_at=created_at - timedelta(minutes=10),
        ),
        api_module.LearningProposal(
            proposal_date=proposal_date,
            proposal_type="prompt_update",
            target_area="promoted_policy",
            title="Already promoted proposal",
            status="promoted",
            canary_percent=100,
            approval_required=False,
            guardrail_metric="conversion_rate",
            idempotency_key="learning:prompt:promoted",
            proposal_json={},
            replay_result_json={},
            created_at=created_at - timedelta(minutes=15),
            updated_at=created_at - timedelta(minutes=15),
        ),
    ]
    fake_session = FakeLearningProposalSession(rows)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        "/v1/admin/autopilot/learning-proposals/summary?limit=2",
        headers={"x-stormlead-operator-token": "test-operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_read_only"
    assert body["source"] == "learning_proposals"
    assert body["endpoint_would_route_live_traffic"] is False
    assert body["endpoint_would_promote_proposal"] is False
    assert body["endpoint_would_contact_provider"] is False
    assert body["endpoint_requires_admin_approval_for_full_rollout"] is True
    assert body["rows_with_full_rollout_intent"] == 0
    assert body["active_count"] == 3
    assert body["pending_replay_count"] == 1
    assert body["rollback_count"] == 1
    assert body["pending_approval_count"] == 1
    assert body["approval_required_count"] == 2
    assert body["max_canary_percent"] == 5
    assert body["by_status"] == {
        "pending_approval": 1,
        "rollback_triggered": 1,
        "pending_replay": 1,
    }
    assert body["by_type"] == {
        "scoring_threshold": 1,
        "prompt_update": 1,
        "cadence_change": 1,
    }
    assert body["by_target_area"] == {
        "qualification": 1,
        "qualification_prompt": 1,
        "follow_up_cadence": 1,
    }
    assert len(body["recent_proposals"]) == 2
    proposal = body["recent_proposals"][0]
    assert proposal["proposal_type"] == "scoring_threshold"
    assert proposal["status"] == "pending_approval"
    assert proposal["canary_percent"] == 5
    assert proposal["proposal"] == {"confidence": 0.82, "target_area": "qualification"}
    assert proposal["replay_result"]["approval_required"] is True
    assert proposal["safety"] == {
        "would_route_live_traffic": False,
        "would_promote_without_admin_approval": False,
        "requires_admin_approval_for_full_rollout": True,
    }
    rollback = body["recent_proposals"][1]
    assert rollback["status"] == "rollback_triggered"
    assert rollback["safety"]["requires_admin_approval_for_full_rollout"] is False
    assert "homeowner@example.com" not in str(body)
    assert "+13215550123" not in str(body)
    assert "promoted_policy" not in str(body)


@pytest.mark.parametrize(
    ("action", "expected_hold"),
    [("hold", True), ("review", True), ("approve", False)],
)
async def test_admin_lead_review_records_hold_and_approve_actions(
    action: str,
    expected_hold: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead_id = uuid4()
    fake_session = FakeLeadReviewSession(lead_id)
    captured: dict[str, object] = {}

    async def fake_latest_state(_session: object, _lead_id) -> api_module.PipelineState:
        return api_module.PipelineState.QUALIFIED

    async def fake_record_transition(*_args: object, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        transition = SimpleNamespace(
            id=uuid4(),
            event_type=kwargs["event_type"],
            status=kwargs["status"],
            payload_json=kwargs["payload"],
        )
        return SimpleNamespace(transition=transition)

    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)
    monkeypatch.setattr(api_module, "latest_state", fake_latest_state)
    monkeypatch.setattr(api_module, "record_transition", fake_record_transition)

    response = await api_module.review_lead(
        lead_id,
        api_module.LeadReviewRequest(action=action, notes="QA review", operator="qa-operator"),
    )

    assert fake_session.flushed is True
    assert fake_session.lead.hold_for_review is expected_hold
    assert response["action"] == action
    assert response["hold_for_review"] is expected_hold
    assert response["timeline_event"]["event_type"] == f"admin.review.{action}"
    assert captured["status"] == "reviewed"
    assert captured["payload"] == {
        "action": action,
        "operator": "qa-operator",
        "notes": "QA review",
        "hold_for_review": expected_hold,
    }


async def test_update_buyer_rejects_active_status_until_activation_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.status = api_module.BuyerStatus.PENDING_VERIFICATION.value
    buyer.sales_stage = api_module.BuyerSalesStage.PROSPECT.value
    buyer.services = []
    buyer.target_zips = []
    buyer.exclusive_zips = []
    buyer.deposit_balance = Decimal("0.00")
    buyer.low_balance_threshold = Decimal("100.00")
    fake_session = FakeBuyerSession(buyer)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    with pytest.raises(api_module.HTTPException) as exc:
        await api_module.update_buyer(
            buyer_id,
            api_module.BuyerUpdateRequest(status=api_module.BuyerStatus.ACTIVE),
        )

    assert exc.value.status_code == 409
    assert "buyer is not activation ready" in str(exc.value.detail)
    assert "terms_accepted" in str(exc.value.detail)


async def test_update_buyer_rechecks_exclusive_zip_conflict_on_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.status = api_module.BuyerStatus.PENDING_VERIFICATION.value
    buyer.sales_stage = api_module.BuyerSalesStage.FUNDED.value
    buyer.services = ["tree_removal"]
    buyer.target_zips = []
    buyer.exclusive_zips = ["32801"]
    buyer.deposit_balance = Decimal("500.00")
    buyer.low_balance_threshold = Decimal("100.00")
    buyer.webhook_secret = "test-secret-32chars-minimum-ok"  # noqa: S105 - inert test HMAC secret
    fake_session = FakeBuyerSession(buyer)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    async def fake_conflict(exclusive_zips: list[str], *, exclude_buyer_id=None) -> None:
        assert exclusive_zips == ["32801"]
        assert exclude_buyer_id == buyer_id
        raise api_module.HTTPException(409, "ZIP conflict with buyers: ['existing']")

    monkeypatch.setattr(api_module, "_assert_no_exclusive_zip_conflict", fake_conflict)

    with pytest.raises(api_module.HTTPException) as exc:
        await api_module.update_buyer(
            buyer_id,
            api_module.BuyerUpdateRequest(status=api_module.BuyerStatus.ACTIVE),
        )

    assert exc.value.status_code == 409
    assert "ZIP conflict" in str(exc.value.detail)


async def test_update_buyer_allows_active_status_when_activation_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.status = api_module.BuyerStatus.PENDING_VERIFICATION.value
    buyer.sales_stage = api_module.BuyerSalesStage.FUNDED.value
    buyer.services = ["tree_removal"]
    buyer.target_zips = []
    buyer.exclusive_zips = ["32801"]
    buyer.deposit_balance = Decimal("500.00")
    buyer.low_balance_threshold = Decimal("100.00")
    buyer.webhook_secret = "test-secret-32chars-minimum-ok"  # noqa: S105 - inert test HMAC secret
    fake_session = FakeBuyerSession(buyer)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    async def no_conflict(exclusive_zips: list[str], *, exclude_buyer_id=None) -> None:
        assert exclusive_zips == ["32801"]
        assert exclude_buyer_id == buyer_id

    monkeypatch.setattr(api_module, "_assert_no_exclusive_zip_conflict", no_conflict)

    response = await api_module.update_buyer(
        buyer_id,
        api_module.BuyerUpdateRequest(status=api_module.BuyerStatus.ACTIVE),
    )

    assert response["status"] == api_module.BuyerStatus.ACTIVE.value
    assert response["onboarding_readiness"]["autopilot_ready"] is True
    assert response["onboarding_readiness"]["coverage_zips"] == ["32801"]


async def test_buyer_sandbox_certification_endpoint_is_dry_run_contract(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.status = api_module.BuyerStatus.PENDING_VERIFICATION.value
    buyer.sales_stage = api_module.BuyerSalesStage.PROSPECT.value
    buyer.services = ["tree_removal"]
    buyer.target_zips = ["32801"]
    buyer.webhook_secret = "test-secret-32chars-minimum-ok"  # noqa: S105 - inert test HMAC secret
    fake_session = FakeBuyerSession(buyer)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    response = await client.get(
        f"/v1/buyers/{buyer_id}/sandbox-certification",
        headers={"Authorization": f"Bearer {buyer.api_key}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "local_sandbox_only"
    assert body["would_contact_buyer"] is False
    assert body["certification_ready"] is True
    assert body["request_contract"]["ping"]["mode_header"] == "X-Stormlead-Mode: ping"
    assert "lead_id" in body["request_contract"]["ping"]["body_fields"]
    assert body["request_contract"]["post"]["mode_header"] == "X-Stormlead-Mode: post"
    assert "Idempotency-Key" in body["request_contract"]["post"]["required_headers"]
    assert body["retry_policy"]["max_attempts"] == api_module.POST_MAX_ATTEMPTS
    assert body["activation_dependency"]["activation_readiness"]["active_status"] is False


def test_buyer_sandbox_certification_reports_missing_contract_requirements() -> None:
    buyer = _test_buyer(uuid4(), "")
    buyer.status = api_module.BuyerStatus.PENDING_VERIFICATION.value
    buyer.services = []
    buyer.target_zips = []
    buyer.exclusive_zips = []
    buyer.webhook_secret = ""

    body = api_module._buyer_sandbox_certification_response(buyer)

    assert body["certification_ready"] is False
    assert body["would_contact_buyer"] is False
    assert set(body["missing_requirements"]) == {
        "service_ready",
        "zip_ready",
        "webhook_ready",
        "api_key_ready",
    }
    assert "active_status" not in body["missing_requirements"]
    assert "wallet_ready" not in body["missing_requirements"]


async def test_update_buyer_rejects_active_buyer_becoming_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buyer_id = uuid4()
    buyer = _test_buyer(buyer_id, f"buyer-{buyer_id.hex}")
    buyer.status = api_module.BuyerStatus.ACTIVE.value
    buyer.sales_stage = api_module.BuyerSalesStage.FUNDED.value
    buyer.services = ["tree_removal"]
    buyer.target_zips = ["32801"]
    buyer.exclusive_zips = []
    buyer.deposit_balance = Decimal("500.00")
    buyer.low_balance_threshold = Decimal("100.00")
    buyer.webhook_secret = "test-secret-32chars-minimum-ok"  # noqa: S105 - inert test HMAC secret
    fake_session = FakeBuyerSession(buyer)
    monkeypatch.setattr(api_module, "get_session", lambda: fake_session)

    with pytest.raises(api_module.HTTPException) as exc:
        await api_module.update_buyer(buyer_id, api_module.BuyerUpdateRequest(services=[]))

    assert exc.value.status_code == 409
    assert "service_ready" in str(exc.value.detail)


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires live DB")
async def test_create_buyer_returns_id(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/buyers",
        json=_buyer_create_payload("http://localhost:9999/buyer"),
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
