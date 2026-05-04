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

from datetime import datetime, timezone
from hashlib import sha256
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
    disclosure_text_hash: str
    form_version: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    consent_timestamp: datetime
    voice_outreach_permitted: bool = True


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

    form_version = _required(answers, "form_version")

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

    disclosure_text_hash = sha256(consent_text.encode("utf-8")).hexdigest()
    provided_disclosure_hash = answers.get("disclosure_text_hash")
    if isinstance(provided_disclosure_hash, str) and provided_disclosure_hash.strip():
        if provided_disclosure_hash.strip().lower() != disclosure_text_hash:
            raise ConsentExtractionError("disclosure_text_hash does not match consent_text")

    source_metadata: dict[str, Any] = {
        "url": meta.url,
        "user_agent": meta.userAgent,
        "country": meta.country,
        "survey_id": envelope.data.surveyId,
        "response_id": envelope.data.id,
        "contact_id": envelope.data.contact.id if envelope.data.contact else None,
        "contact_user_id": envelope.data.contact.userId if envelope.data.contact else None,
    }
    source_metadata = {k: v for k, v in source_metadata.items() if v is not None}

    voice_outreach_permitted = answers.get("voice_outreach_permitted", True)
    if not isinstance(voice_outreach_permitted, bool):
        voice_outreach_permitted = True

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
        disclosure_text_hash=disclosure_text_hash,
        form_version=form_version,
        source_metadata=source_metadata,
        consent_timestamp=datetime.now(timezone.utc),
        voice_outreach_permitted=voice_outreach_permitted,
    )
