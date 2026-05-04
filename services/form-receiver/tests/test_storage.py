"""unit tests for the formbricks → ExtractedConsent projection.

db-touching tests (upsert_lead, record_audit) live in scripts/smoke_e2e.py
since they need a real postgres + the migration applied.
"""

from __future__ import annotations

import pytest
from form_receiver.schemas import (
    ConsentExtractionError,
    FormbricksEnvelope,
    extract_consent,
)


def _envelope(answers: dict, *, ttc: dict | None = None) -> FormbricksEnvelope:
    return FormbricksEnvelope.model_validate(
        {
            "event": "responseFinished",
            "webhookId": "wh_test",
            "data": {
                "id": "resp_test",
                "surveyId": "survey_test",
                "data": answers,
                "ttc": ttc or {},
                "meta": {
                    "url": "http://localhost:3000/test",
                    "userAgent": "Mozilla/5.0 (test)",
                },
                "finished": True,
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


def test_extract_consent_evidence_fields() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
            "form_version": "v2026-05-01",
            "voice_outreach_permitted": False,
        }
    )
    out = extract_consent(e)
    assert out.form_version == "v2026-05-01"
    assert len(out.disclosure_text_hash) == 64
    assert out.source_metadata["survey_id"] == "survey_test"
    assert out.voice_outreach_permitted is False


def test_disclosure_hash_mismatch_raises() -> None:
    e = _envelope(
        {
            "name": "T",
            "phone": "+15125550123",
            "address_line1": "1 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "consent_text": "I agree to be contacted.",
            "form_version": "v2026-05-01",
            "disclosure_text_hash": "deadbeef",
        }
    )
    with pytest.raises(ConsentExtractionError):
        extract_consent(e)
