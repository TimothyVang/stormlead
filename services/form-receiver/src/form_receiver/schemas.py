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

import json
import os
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator, model_validator


class CallOutcome(StrEnum):
    answered = "answered"
    voicemail = "voicemail"
    no_answer = "no_answer"
    busy = "busy"


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
    consent_version: str = "tree-damage-intake-v1"
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

    # campaign and buyer-routing attribution from hidden form fields/contact attrs
    requested_service: str | None = None
    damage_description: str | None = None
    damage_type: str | None = None
    urgency: str | None = None
    power_line_involved: bool | None = None
    injury_reported: bool | None = None
    active_danger: bool | None = None
    safety_flags: list[str] = Field(default_factory=list)
    campaign_id: str | None = None
    campaign_source: str | None = None
    first_touch_source: str | None = None
    last_touch_source: str | None = None
    google_click_id: str | None = None
    trustedform_cert_url: str | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    gps_accuracy_meters: float | None = None
    gps_captured_at: datetime | None = None
    location_source: str | None = None
    location_confirmed_at: datetime | None = None
    location_verification_status: str | None = None
    photo_s3_keys: list[str] = Field(default_factory=list)


class SuppressionRequest(BaseModel):
    """Consumer opt-out request used by the local privacy endpoint."""

    phone: str | None = Field(default=None, min_length=7, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    reason: str = Field(default="consumer_opt_out", min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_contact(self) -> SuppressionRequest:
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        return _e164(value) if value else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError as e:
            raise ValueError("email is invalid") from e


class ConsentExtractionError(ValueError):
    """raised when required consent fields are missing or invalid."""


DEFAULT_CONSENT_VERSION = "tree-damage-intake-v1"
CONSENT_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


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


def _optional_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _current_consent_version() -> str:
    return (
        os.getenv("STORMLEAD_CONSENT_VERSION", DEFAULT_CONSENT_VERSION).strip()
        or DEFAULT_CONSENT_VERSION
    )


def _allowed_consent_versions() -> set[str]:
    configured = os.getenv("STORMLEAD_ALLOWED_CONSENT_VERSIONS", "").strip()
    raw_versions = configured.split(",") if configured else [_current_consent_version()]
    return {version.strip() for version in raw_versions if version.strip()}


def _validate_consent_version(value: str | None) -> str:
    version = (value or "").strip()
    if not version:
        raise ConsentExtractionError("missing required field 'consent_version'")
    if not CONSENT_VERSION_RE.fullmatch(version):
        raise ConsentExtractionError("invalid consent_version")
    if version not in _allowed_consent_versions():
        raise ConsentExtractionError("unapproved consent_version")
    return version


def _truthy_env(name: str, default: str = "false") -> bool:
    return _truthy(os.getenv(name, default))


def _optional_float(value: Any, *, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ConsentExtractionError(f"invalid {field_name}") from e


def _optional_datetime(value: Any, *, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as e:
            raise ConsentExtractionError(f"invalid {field_name}") from e
    raise ConsentExtractionError(f"invalid {field_name}")


def _text_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                return _text_list(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return []


def _hidden_value(envelope: FormbricksEnvelope, answers: dict[str, Any], key: str) -> str | None:
    return _optional_text(
        answers.get(key),
        envelope.data.contactAttributes.get(key),
        envelope.data.variables.get(key),
    )


def _safety_flags(
    *,
    damage_type: str | None,
    urgency: str | None,
    power_line_involved: bool | None,
    injury_reported: bool | None,
    active_danger: bool | None,
) -> list[str]:
    flags: list[str] = []
    if power_line_involved:
        flags.append("power_line")
    if injury_reported:
        flags.append("injury")
    if active_danger:
        flags.append("active_danger")
    if damage_type == "roof_impact":
        flags.append("roof_impact")
    if damage_type in {"tree_on_structure", "structure_impact"}:
        flags.append("structure_impact")
    if urgency == "emergency":
        flags.append("emergency")
    return sorted(set(flags))


def extract_consent(envelope: FormbricksEnvelope) -> ExtractedConsent:
    """project the envelope into our consent shape; raise on missing required fields."""
    answers = envelope.data.data
    meta = envelope.data.meta

    if not (meta and meta.url and meta.userAgent):
        raise ConsentExtractionError("missing meta.url or meta.userAgent")

    # required tcpa fields
    consent_text = _required(answers, "consent_text")
    consent_version = _validate_consent_version(
        _optional_text(_hidden_value(envelope, answers, "consent_version"))
    )
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
    damage_description = _optional_text(
        _hidden_value(envelope, answers, "damage_description"),
        _hidden_value(envelope, answers, "description"),
    )
    damage_type = _optional_text(_hidden_value(envelope, answers, "damage_type"))
    urgency = _optional_text(_hidden_value(envelope, answers, "urgency"))
    power_line_involved = _optional_bool(_hidden_value(envelope, answers, "power_line_involved"))
    injury_reported = _optional_bool(_hidden_value(envelope, answers, "injury_reported"))
    active_danger = _optional_bool(_hidden_value(envelope, answers, "active_danger"))
    safety_flags = _safety_flags(
        damage_type=damage_type,
        urgency=urgency,
        power_line_involved=power_line_involved,
        injury_reported=injury_reported,
        active_danger=active_danger,
    )

    # dwell: prefer the hidden field if present, else sum ttc per-question values
    dwell_ms: int | None = None
    raw_dwell = answers.get("dwell_ms")
    if isinstance(raw_dwell, (int, float)):
        dwell_ms = int(raw_dwell)
    else:
        ttc_total = sum(int(v) for v in envelope.data.ttc.values() if isinstance(v, (int, float)))
        if ttc_total > 0:
            dwell_ms = ttc_total

    campaign_source = _optional_text(
        _hidden_value(envelope, answers, "campaign_source"),
        _hidden_value(envelope, answers, "utm_source"),
    )
    first_touch_source = _optional_text(
        _hidden_value(envelope, answers, "first_touch_source"),
        campaign_source,
    )
    last_touch_source = _optional_text(
        _hidden_value(envelope, answers, "last_touch_source"),
        campaign_source,
    )
    require_location_photo_verification = _truthy_env(
        "FORM_RECEIVER_REQUIRE_LOCATION_PHOTO_VERIFICATION", "true"
    ) or _truthy(_hidden_value(envelope, answers, "require_location_photo_verification"))
    gps_latitude = _optional_float(
        _hidden_value(envelope, answers, "gps_latitude"), field_name="gps_latitude"
    )
    gps_longitude = _optional_float(
        _hidden_value(envelope, answers, "gps_longitude"), field_name="gps_longitude"
    )
    gps_accuracy_meters = _optional_float(
        _hidden_value(envelope, answers, "gps_accuracy_meters"),
        field_name="gps_accuracy_meters",
    )
    gps_captured_at = _optional_datetime(
        _hidden_value(envelope, answers, "gps_captured_at"), field_name="gps_captured_at"
    )
    location_confirmed_at = _optional_datetime(
        _hidden_value(envelope, answers, "location_confirmed_at"),
        field_name="location_confirmed_at",
    )
    photo_s3_keys = _text_list(
        answers.get("damage_photo_keys")
        or envelope.data.contactAttributes.get("damage_photo_keys")
        or envelope.data.variables.get("damage_photo_keys")
    )
    if require_location_photo_verification:
        if gps_latitude is None or gps_longitude is None:
            raise ConsentExtractionError("missing required GPS location")
        if not (-90 <= gps_latitude <= 90) or not (-180 <= gps_longitude <= 180):
            raise ConsentExtractionError("GPS location is outside valid latitude/longitude bounds")
        if gps_accuracy_meters is None or gps_accuracy_meters > 500:
            raise ConsentExtractionError("GPS accuracy is too low; please retake location")
        if gps_captured_at is None:
            raise ConsentExtractionError("missing GPS capture timestamp")
        if location_confirmed_at is None:
            raise ConsentExtractionError("missing location confirmation")
        if len(photo_s3_keys) < 2:
            raise ConsentExtractionError("at least two damage photos are required")
    location_verification_status = "verified" if require_location_photo_verification else None

    return ExtractedConsent(
        formbricks_response_id=envelope.data.id,
        page_url=meta.url,
        user_agent=meta.userAgent,
        consent_text=consent_text,
        consent_version=consent_version,
        name=name,
        phone_e164=phone,
        email=email,
        address_line1=address_line1,
        city=city,
        state=state.upper()[:2],
        zip=zip_,
        page_html_sha256=page_html_sha256,
        dwell_ms=dwell_ms,
        requested_service=_optional_text(
            _hidden_value(envelope, answers, "requested_service"),
            _hidden_value(envelope, answers, "service"),
        ),
        damage_description=damage_description,
        damage_type=damage_type,
        urgency=urgency,
        power_line_involved=power_line_involved,
        injury_reported=injury_reported,
        active_danger=active_danger,
        safety_flags=safety_flags,
        campaign_id=_optional_text(
            _hidden_value(envelope, answers, "campaign_id"),
            _hidden_value(envelope, answers, "utm_campaign"),
        ),
        campaign_source=campaign_source,
        first_touch_source=first_touch_source,
        last_touch_source=last_touch_source,
        google_click_id=_optional_text(_hidden_value(envelope, answers, "gclid")),
        trustedform_cert_url=_hidden_value(envelope, answers, "trustedform_cert_url"),
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        gps_accuracy_meters=gps_accuracy_meters,
        gps_captured_at=gps_captured_at,
        location_source=_optional_text(_hidden_value(envelope, answers, "location_source")),
        location_confirmed_at=location_confirmed_at,
        location_verification_status=location_verification_status,
        photo_s3_keys=photo_s3_keys,
    )
