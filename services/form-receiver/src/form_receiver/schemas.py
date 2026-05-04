"""pydantic schemas for the formbricks envelope + extracted consent shape.

the form template *must* expose specific question IDs for us to extract:
  name, phone, email, address_line1, city, state, zip, consent_text

plus two hidden fields set by client-side JS at form-load:
  page_html_sha256  sha256 of document.documentElement.outerHTML at load
  dwell_ms          (optional; otherwise computed from envelope.data.ttc)

if any required field is missing, validate_consent() raises and the
api returns 400. that's intentional: a form lacking these is not a
defensible consent capture.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field


class FormbricksMeta(BaseModel):
    url: str | None = None
    userAgent: str | None = None  # noqa: N815 - external Formbricks field
    country: str | None = None


class FormbricksContact(BaseModel):
    id: str | None = None
    userId: str | None = None  # noqa: N815 - external Formbricks field


class FormbricksResponseData(BaseModel):
    """inner `data` of the envelope."""

    id: str  # response_id
    surveyId: str  # noqa: N815 - external Formbricks field
    data: dict[str, Any] = Field(default_factory=dict)  # question_id → answer
    ttc: dict[str, Any] = Field(default_factory=dict)  # time-to-completion per q
    contact: FormbricksContact | None = None
    contactAttributes: dict[str, Any] = Field(  # noqa: N815 - external Formbricks field
        default_factory=dict
    )
    meta: FormbricksMeta | None = None
    finished: bool = False
    endingId: str | None = None  # noqa: N815 - external Formbricks field
    variables: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class FormbricksEnvelope(BaseModel):
    event: str
    webhookId: str  # noqa: N815 - external Formbricks field
    data: FormbricksResponseData


class ExtractedConsent(BaseModel):
    """projection of the envelope into the fields we persist.

    populated by extract_consent(envelope). consumed by storage.persist_lead +
    storage.record_audit. never returned over the network.
    """

    formbricks_response_id: str
    page_url: str
    user_agent: str

    # tcpa-required fields
    consent_text: str
    name: str
    phone_e164: str
    email: str | None = None
    address_line1: str
    city: str
    state: str
    zip: str

    # tamper-evidence
    page_html_sha256: str | None = None
    dwell_ms: int | None = None
    consent_text_version: str = "v1"
    consent_proof_sha256: str

    # quality gate
    quality_score: float
    quality_reasons: list[str] = Field(default_factory=list)


class ConsentExtractionError(ValueError):
    """raised when required consent fields are missing or invalid."""


def _required(answers: dict[str, Any], key: str) -> str:
    val = answers.get(key)
    if not val or not isinstance(val, str):
        raise ConsentExtractionError(f"missing required field '{key}'")
    return val.strip()


def _e164(phone_raw: str) -> str:
    try:
        parsed = phonenumbers.parse(phone_raw, "US")
    except phonenumbers.NumberParseException as e:
        raise ConsentExtractionError(f"invalid phone: {e}") from e
    if not phonenumbers.is_valid_number(parsed):
        raise ConsentExtractionError("invalid phone (not a valid number)")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _valid_email(email_raw: str | None) -> str | None:
    if not email_raw:
        return None
    try:
        return validate_email(email_raw, check_deliverability=False).normalized
    except EmailNotValidError:
        return None  # silently drop invalid email; phone is the primary identifier


def extract_consent(envelope: FormbricksEnvelope) -> ExtractedConsent:
    """project the envelope into our consent shape; raise on missing required fields."""
    answers = envelope.data.data
    meta = envelope.data.meta

    if not (meta and meta.url and meta.userAgent):
        raise ConsentExtractionError("missing meta.url or meta.userAgent")

    # required tcpa fields
    consent_text = _required(answers, "consent_text")
    name = _required(answers, "name")
    phone = _e164(_required(answers, "phone"))
    address_line1 = _required(answers, "address_line1")
    city = _required(answers, "city")
    state = _required(answers, "state")
    zip_ = _required(answers, "zip")

    # optional
    email = _valid_email(answers.get("email"))
    page_html_sha256 = answers.get("page_html_sha256")
    if page_html_sha256 is not None and not isinstance(page_html_sha256, str):
        page_html_sha256 = None

    # dwell: prefer the hidden field if present, else sum ttc per-question values
    dwell_ms: int | None = None
    raw_dwell = answers.get("dwell_ms")
    if isinstance(raw_dwell, (int, float)):
        dwell_ms = int(raw_dwell)
    else:
        ttc_total = sum(int(v) for v in envelope.data.ttc.values() if isinstance(v, (int, float)))
        if ttc_total > 0:
            dwell_ms = ttc_total

    quality_score, quality_reasons = _quality_score(
        phone=phone, email=email, consent_text=consent_text, dwell_ms=dwell_ms
    )
    proof_payload = {
        "response_id": envelope.data.id,
        "consent_text": consent_text,
        "name": name,
        "phone_e164": phone,
        "address_line1": address_line1,
        "city": city,
        "state": state.upper()[:2],
        "zip": zip_,
        "page_url": meta.url,
        "user_agent": meta.userAgent,
        "page_html_sha256": page_html_sha256,
    }
    consent_proof_sha256 = hashlib.sha256(
        json.dumps(proof_payload, sort_keys=True).encode()
    ).hexdigest()
    return ExtractedConsent(
        formbricks_response_id=envelope.data.id,
        page_url=meta.url,
        user_agent=meta.userAgent,
        consent_text=consent_text,
        name=name,
        phone_e164=phone,
        email=email,
        address_line1=address_line1,
        city=city,
        state=state.upper()[:2],
        zip=zip_,
        page_html_sha256=page_html_sha256,
        dwell_ms=dwell_ms,
        consent_proof_sha256=consent_proof_sha256,
        quality_score=quality_score,
        quality_reasons=quality_reasons,
    )


def _quality_score(
    *,
    phone: str,
    email: str | None,
    consent_text: str,
    dwell_ms: int | None,
) -> tuple[float, list[str]]:
    score = 1.0
    reasons: list[str] = []
    if len(consent_text.strip()) < 20:
        score -= 0.35
        reasons.append("consent_text_too_short")
    if dwell_ms is not None and dwell_ms < 1200:
        score -= 0.25
        reasons.append("low_dwell_time")
    if not email:
        score -= 0.1
        reasons.append("missing_or_invalid_email")
    if not phone.startswith("+1"):
        score -= 0.1
        reasons.append("non_us_phone")
    return max(0.0, round(score, 3)), reasons
