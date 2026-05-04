"""unit tests for the formbricks → ExtractedConsent projection.

db-touching tests (upsert_lead, record_audit) live in scripts/smoke_e2e.py
since they need a real postgres + the migration applied.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from form_receiver.schemas import (
    ConsentExtractionError,
    FormbricksEnvelope,
    SuppressionRequest,
    extract_consent,
)
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
) -> FormbricksEnvelope:
    return FormbricksEnvelope.model_validate(
        {
            "event": "responseFinished",
            "webhookId": "wh_test",
            "data": {
                "id": "resp_test",
                "surveyId": "survey_test",
                "data": answers,
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
