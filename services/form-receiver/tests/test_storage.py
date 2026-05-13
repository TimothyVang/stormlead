"""unit tests for the formbricks → ExtractedConsent projection.

db-touching tests (upsert_lead, record_audit) live in scripts/smoke_e2e.py
since they need a real postgres + the migration applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from form_receiver.schemas import (
    ConsentExtractionError,
    ExtractedConsent,
    FormbricksEnvelope,
    SuppressionRequest,
    extract_consent,
)
from form_receiver.storage import DuplicateLeadError, record_suppression, upsert_lead
from stormlead_core.dedup import (
    build_duplicate_window,
    initial_quality_score,
)


def _envelope(
    answers: dict,
    *,
    ttc: dict | None = None,
    contact_attributes: dict | None = None,
    variables: dict | None = None,
    with_location_photo: bool = True,
    with_consent_version: bool = True,
) -> FormbricksEnvelope:
    envelope_answers = dict(answers)
    if with_consent_version:
        envelope_answers = {"consent_version": "tree-damage-intake-v1", **envelope_answers}
    if with_location_photo:
        envelope_answers = {
            "gps_latitude": "30.4515",
            "gps_longitude": "-91.1871",
            "gps_accuracy_meters": "22",
            "gps_captured_at": "2026-05-10T18:00:00Z",
            "location_source": "browser_gps",
            "location_confirmed_at": "2026-05-10T18:01:00Z",
            "damage_photo_keys": '["wide.jpg", "close.jpg"]',
            **envelope_answers,
        }
    return FormbricksEnvelope.model_validate(
        {
            "event": "responseFinished",
            "webhookId": "wh_test",
            "data": {
                "id": "resp_test",
                "surveyId": "survey_test",
                "data": envelope_answers,
                "ttc": ttc or {},
                "contactAttributes": contact_attributes or {},
                "meta": {
                    "url": "http://localhost:3000/test",
                    "userAgent": "Mozilla/5.0 (test)",
                },
                "finished": True,
                "variables": variables or {},
            },
        }
    )


def test_extract_minimum_required_fields() -> None:
    e = _envelope(
        {
            "name": "Test User",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
        }
    )
    out = extract_consent(e)
    assert out.name == "Test User"
    assert out.phone_e164 == "+15125550123"
    assert out.state == "TX"
    assert out.zip == "78701"
    assert out.email is None  # optional, omitted
    assert out.consent_version == "tree-damage-intake-v1"


def test_extract_consent_version_from_hidden_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "STORMLEAD_ALLOWED_CONSENT_VERSIONS", "tree-damage-intake-v1,tree-damage-intake-v2"
    )
    e = _envelope(
        {
            "name": "Test User",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
        },
        contact_attributes={"consent_version": "tree-damage-intake-v2"},
        with_consent_version=False,
    )
    out = extract_consent(e)
    assert out.consent_version == "tree-damage-intake-v2"


def test_extract_missing_consent_version_raises() -> None:
    e = _envelope(
        {
            "name": "Test User",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
        },
        with_consent_version=False,
    )
    with pytest.raises(ConsentExtractionError, match="consent_version"):
        extract_consent(e)


def test_extract_invalid_consent_version_raises() -> None:
    e = _envelope(
        {
            "name": "Test User",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
            "consent_version": "Not Legal Copy V2!",
        },
    )
    with pytest.raises(ConsentExtractionError, match="invalid consent_version"):
        extract_consent(e)


def test_extract_unapproved_consent_version_raises() -> None:
    e = _envelope(
        {
            "name": "Test User",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
            "consent_version": "tree-damage-intake-v2",
        },
    )
    with pytest.raises(ConsentExtractionError, match="unapproved consent_version"):
        extract_consent(e)


def test_extract_normalizes_us_phone_to_e164() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "(512) 555-0123",  # NANP, will normalize
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
        }
    )
    out = extract_consent(e)
    assert out.phone_e164 == "+15125550123"


def test_extract_invalid_phone_raises() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "not-a-phone",
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
        }
    )
    with pytest.raises(ConsentExtractionError):
        extract_consent(e)


def test_extract_missing_consent_text_raises() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            # consent_text deliberately absent
        }
    )
    with pytest.raises(ConsentExtractionError):
        extract_consent(e)


def test_extract_dwell_from_ttc_sum() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
        },
        ttc={"q1": 1500, "q2": 2300, "q3": 800},
    )
    out = extract_consent(e)
    assert out.dwell_ms == 1500 + 2300 + 800


def test_extract_state_uppercases_and_truncates() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "A",
            "state": "tx",  # lowercase
            "zip": "78701",
            "consent_text": "x",
        }
    )
    out = extract_consent(e)
    assert out.state == "TX"


def test_extract_invalid_email_dropped_silently() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "email": "not-an-email",
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
        }
    )
    out = extract_consent(e)
    assert out.email is None  # phone is the primary identifier


def test_extract_campaign_attribution_from_hidden_fields() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "A",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
            "requested_service": "tree_removal",
            "utm_source": "google_lsa",
        },
        contact_attributes={"campaign_id": "spring-storm-austin"},
        variables={"last_touch_source": "retargeting"},
    )
    out = extract_consent(e)
    assert out.requested_service == "tree_removal"
    assert out.campaign_id == "spring-storm-austin"
    assert out.campaign_source == "google_lsa"
    assert out.first_touch_source == "google_lsa"
    assert out.last_touch_source == "retargeting"


def test_extract_tree_damage_safety_fields() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "x",
            "damage_type": "roof_impact",
            "urgency": "emergency",
            "damage_description": "Tree limb is on the roof near a service line.",
            "power_line_involved": "true",
            "injury_reported": "false",
            "active_danger": "yes",
        }
    )

    out = extract_consent(e)

    assert out.damage_type == "roof_impact"
    assert out.urgency == "emergency"
    assert out.damage_description == "Tree limb is on the roof near a service line."
    assert out.power_line_involved is True
    assert out.injury_reported is False
    assert out.active_danger is True
    assert out.safety_flags == ["active_danger", "emergency", "power_line", "roof_impact"]


def test_extract_location_photo_verification_fields() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "Baton Rouge",
            "state": "LA",
            "zip": "70802",
            "consent_text": "x",
            "require_location_photo_verification": "true",
            "gps_latitude": "30.4515",
            "gps_longitude": "-91.1871",
            "gps_accuracy_meters": "22",
            "gps_captured_at": "2026-05-10T18:00:00Z",
            "location_source": "browser_gps",
            "location_confirmed_at": "2026-05-10T18:01:00Z",
            "location_verification_status": "client-spoofed",
            "damage_photo_keys": '["wide.jpg", "close.jpg"]',
            "gclid": "test-gclid",
        },
        contact_attributes={"campaign_id": "baton-rouge-storm-test"},
    )
    out = extract_consent(e)
    assert out.gps_latitude == 30.4515
    assert out.gps_longitude == -91.1871
    assert out.gps_accuracy_meters == 22
    assert out.location_source == "browser_gps"
    assert out.location_verification_status == "verified"
    assert out.photo_s3_keys == ["wide.jpg", "close.jpg"]
    assert out.google_click_id == "test-gclid"


def test_extract_location_photo_verification_requires_two_photos() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "Baton Rouge",
            "state": "LA",
            "zip": "70802",
            "consent_text": "x",
            "require_location_photo_verification": "true",
            "gps_latitude": "30.4515",
            "gps_longitude": "-91.1871",
            "gps_accuracy_meters": "22",
            "gps_captured_at": "2026-05-10T18:00:00Z",
            "location_confirmed_at": "2026-05-10T18:01:00Z",
            "damage_photo_keys": '["wide.jpg"]',
        }
    )
    with pytest.raises(ConsentExtractionError, match="two damage photos"):
        extract_consent(e)


def test_extract_location_photo_verification_required_by_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORM_RECEIVER_REQUIRE_LOCATION_PHOTO_VERIFICATION", "true")
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "Baton Rouge",
            "state": "LA",
            "zip": "70802",
            "consent_text": "x",
        },
        with_location_photo=False,
    )
    with pytest.raises(ConsentExtractionError, match="missing required GPS location"):
        extract_consent(e)


def test_extract_location_photo_verification_requires_gps_timestamp() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1",
            "city": "Baton Rouge",
            "state": "LA",
            "zip": "70802",
            "consent_text": "x",
            "gps_captured_at": "",
        }
    )
    with pytest.raises(ConsentExtractionError, match="GPS capture timestamp"):
        extract_consent(e)


def test_suppression_request_requires_contact() -> None:
    with pytest.raises(ValueError):
        SuppressionRequest.model_validate({})


def test_suppression_request_normalizes_contact() -> None:
    request = SuppressionRequest.model_validate(
        {"phone": "(512) 555-0123", "email": "USER@Example.COM"}
    )
    assert request.phone == "+15125550123"
    assert request.email == "USER@example.com"


def test_duplicate_window_normalizes_phone_and_address() -> None:
    window = build_duplicate_window(
        phone="(512) 555-0100",
        address_line1="100 Main St.",
        city="Austin",
        state="tx",
        zip_code="78701",
        storm_id=None,
        submitted_at=datetime.now(UTC),
        lookback_hours=48,
    )
    assert window.phone_norm == "5125550100"
    assert "100 MAIN ST" in window.address_norm


def test_initial_quality_score_flags_duplicate_and_low_quality() -> None:
    q = initial_quality_score(dwell_ms=500, has_email=False, duplicate=True)
    assert q.blocked is True
    assert q.hold is True
    assert q.score < 0.6
    assert "duplicate_window_match" in q.reason


def test_initial_quality_score_holds_safety_flags_without_fraud_block() -> None:
    q = initial_quality_score(
        dwell_ms=5000,
        has_email=True,
        duplicate=False,
        photo_count=2,
        location_verified=True,
        urgency="emergency",
        safety_flags=["power_line"],
    )
    assert q.blocked is False
    assert q.hold is True
    assert "safety_review_required:power_line" in q.reason


class _FakeResult:
    def __init__(self, first_value: object | None = None) -> None:
        self._first_value = first_value

    def first(self) -> object | None:
        return self._first_value

    def scalars(self) -> _FakeResult:
        return self


class _FakeSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self.results = results
        self.execute_count = 0
        self.statements: list[object] = []
        self.added: list[object] = []

    async def execute(self, statement: object) -> _FakeResult:
        self.execute_count += 1
        self.statements.append(statement)
        return self.results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def _extracted_consent(*, page_hash: str = "a" * 64) -> ExtractedConsent:
    return extract_consent(
        _envelope(
            {
                "name": "Test User",
                "phone": "+15125550123",
                "email": "test@example.com",
                "address_line1": "100 Main St",
                "city": "Austin",
                "state": "TX",
                "zip": "78701",
                "consent_text": "I agree to be contacted.",
                "requested_service": "tree_removal",
                "damage_type": "fallen_tree",
                "urgency": "same_day",
                "damage_description": "Fallen tree across the driveway.",
                "power_line_involved": "false",
                "injury_reported": "false",
                "active_danger": "false",
                "page_html_sha256": page_hash,
            }
        )
    )


@pytest.mark.asyncio
async def test_upsert_lead_hard_rejects_recent_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    duplicate_id = uuid4()
    session = _FakeSession(
        [
            _FakeResult(None),
            _FakeResult(None),
            _FakeResult(SimpleNamespace(id=duplicate_id)),
        ]
    )
    monkeypatch.setattr(
        "form_receiver.storage.get_session",
        lambda: _FakeSessionContext(session),
    )

    with pytest.raises(DuplicateLeadError) as exc_info:
        await upsert_lead(_extracted_consent(page_hash="b" * 64), ip="127.0.0.1")

    assert exc_info.value.duplicate_lead_id == duplicate_id
    assert exc_info.value.reason == "duplicate_window_match"
    assert exc_info.value.window_hours == 72
    assert session.execute_count == 3
    assert "requested_service" not in str(session.statements[2])
    assert session.added == []


@pytest.mark.asyncio
async def test_upsert_lead_rechecks_webhook_id_after_duplicate_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = uuid4()
    session = _FakeSession(
        [
            _FakeResult(None),
            _FakeResult(None),
            _FakeResult(None),
            _FakeResult(SimpleNamespace(id=existing_id)),
        ]
    )
    monkeypatch.setattr(
        "form_receiver.storage.get_session",
        lambda: _FakeSessionContext(session),
    )

    lead_id, created = await upsert_lead(
        _extracted_consent(), ip="127.0.0.1", webhook_id="evt_retry_race"
    )

    assert lead_id == existing_id
    assert created is False
    assert session.execute_count == 4


@pytest.mark.asyncio
async def test_record_suppression_reselects_existing_on_insert_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = uuid4()
    session = _FakeSession(
        [_FakeResult(None), _FakeResult(SimpleNamespace(id=existing_id, status="active"))]
    )
    monkeypatch.setattr(
        "form_receiver.storage.get_session",
        lambda: _FakeSessionContext(session),
    )

    suppression_id, created = await record_suppression(
        phone_e164="+15125550123",
        email=None,
        reason="consumer_opt_out",
        source="unit_test",
    )

    assert suppression_id == existing_id
    assert created is False
    assert session.execute_count == 2


@pytest.mark.asyncio
async def test_record_suppression_reactivates_inactive_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = uuid4()
    session = _FakeSession(
        [
            _FakeResult(None),
            _FakeResult(SimpleNamespace(id=existing_id, status="inactive")),
            _FakeResult(None),
        ]
    )
    monkeypatch.setattr(
        "form_receiver.storage.get_session",
        lambda: _FakeSessionContext(session),
    )

    suppression_id, created = await record_suppression(
        phone_e164="+15125550123",
        email=None,
        reason="consumer_opt_out",
        source="unit_test",
    )

    assert suppression_id == existing_id
    assert created is False
    assert session.execute_count == 3
    assert "UPDATE suppression_entries" in str(session.statements[2])
