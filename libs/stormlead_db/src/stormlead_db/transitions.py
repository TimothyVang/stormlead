"""Lead pipeline transition audit helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from stormlead_core import PipelineState, assert_transition

from stormlead_db.tables import LeadStateTransition

ACTIVE_TRANSITION_STATUSES = frozenset({"started"})
SUCCESS_TRANSITION_STATUSES = frozenset({"succeeded", "reviewed"})
MAX_TIMELINE_PAYLOAD_ITEMS = 8
MAX_TIMELINE_STRING_LENGTH = 240

_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "address",
        "address_line1",
        "api_key",
        "authorization",
        "contact_email",
        "contact_phone_e164",
        "consent_ip",
        "consent_text",
        "consent_user_agent",
        "email",
        "full_name",
        "name",
        "password",
        "phone",
        "phone_e164",
        "prompt",
        "raw_payload",
        "response_body",
        "secret",
        "system_prompt",
        "token",
        "trustedform_cert_url",
        "user_prompt",
        "webhook_secret",
    }
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "api_key",
        "authorization",
        "consent",
        "password",
        "prompt",
        "raw",
        "secret",
        "token",
        "webhook_secret",
    }
)
_ARTIFACT_KEY_PARTS = ("artifact", "evidence", "screenshot", "trace", "video")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_E164_RE = re.compile(r"\+\d{8,15}")


@dataclass(frozen=True)
class TransitionWriteResult:
    transition: LeadStateTransition
    inserted: bool


@dataclass(frozen=True)
class LeadTimelineEvent:
    id: UUID
    lead_id: UUID
    sequence: int
    from_state: str
    to_state: str
    event_type: str
    task_name: str | None
    workflow_run_id: str | None
    status: str
    created_at: datetime
    payload_summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "lead_id": str(self.lead_id),
            "sequence": self.sequence,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "event_type": self.event_type,
            "task_name": self.task_name,
            "workflow_run_id": self.workflow_run_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "payload_summary": self.payload_summary,
        }


@dataclass(frozen=True)
class LeadRunSummary:
    lead_id: UUID
    workflow_run_id: str | None
    current_state: str
    status: str
    event_count: int
    error_count: int
    review_count: int
    started_at: datetime
    updated_at: datetime
    latest_event_type: str
    artifact_paths: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "lead_id": str(self.lead_id),
            "workflow_run_id": self.workflow_run_id,
            "current_state": self.current_state,
            "status": self.status,
            "event_count": self.event_count,
            "error_count": self.error_count,
            "review_count": self.review_count,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "latest_event_type": self.latest_event_type,
            "artifact_paths": self.artifact_paths,
        }


def build_transition_idempotency_key(
    *,
    lead_id: UUID,
    from_state: PipelineState | str | None,
    to_state: PipelineState | str,
    event_type: str,
    task_name: str | None = None,
    version: str = "v1",
) -> str:
    raw = ":".join(
        [
            version,
            str(lead_id),
            str(from_state) if from_state is not None else "start",
            str(to_state),
            event_type,
            task_name or "",
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_transition_by_idempotency_key(
    session: AsyncSession, idempotency_key: str
) -> LeadStateTransition | None:
    return await session.scalar(
        select(LeadStateTransition).where(LeadStateTransition.idempotency_key == idempotency_key)
    )


async def record_transition(
    session: AsyncSession,
    *,
    lead_id: UUID,
    from_state: PipelineState | str | None,
    to_state: PipelineState | str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    task_name: str | None = None,
    workflow_run_id: str | None = None,
    status: str = "succeeded",
) -> TransitionWriteResult:
    if from_state is not None:
        assert_transition(from_state, to_state)
    key = idempotency_key or build_transition_idempotency_key(
        lead_id=lead_id,
        from_state=from_state,
        to_state=to_state,
        event_type=event_type,
        task_name=task_name,
    )
    transition_id = uuid4()
    stmt = (
        pg_insert(LeadStateTransition)
        .values(
            id=transition_id,
            lead_id=lead_id,
            from_state=str(from_state) if from_state is not None else "start",
            to_state=str(to_state),
            event_type=event_type,
            task_name=task_name,
            workflow_run_id=workflow_run_id,
            status=status,
            idempotency_key=key,
            payload_json=payload or {},
        )
        .on_conflict_do_nothing(constraint="uq_lead_state_transitions_idempotency_key")
        .returning(LeadStateTransition)
    )
    try:
        inserted = (await session.execute(stmt)).scalar_one_or_none()
    except IntegrityError:
        inserted = None
    if inserted is not None:
        return TransitionWriteResult(transition=inserted, inserted=True)
    existing = await get_transition_by_idempotency_key(session, key)
    if existing is None:
        raise RuntimeError("transition idempotency conflict without existing transition row")
    return TransitionWriteResult(transition=existing, inserted=False)


async def latest_transition(session: AsyncSession, lead_id: UUID) -> LeadStateTransition | None:
    return await session.scalar(
        select(LeadStateTransition)
        .where(LeadStateTransition.lead_id == lead_id)
        .order_by(LeadStateTransition.created_at.desc())
        .limit(1)
    )


async def latest_state(session: AsyncSession, lead_id: UUID) -> PipelineState | None:
    transition = await latest_transition(session, lead_id)
    return PipelineState(transition.to_state) if transition is not None else None


async def has_active_transition(session: AsyncSession, lead_id: UUID) -> bool:
    active_id = await session.scalar(
        select(LeadStateTransition.id)
        .where(
            LeadStateTransition.lead_id == lead_id,
            LeadStateTransition.status.in_(ACTIVE_TRANSITION_STATUSES),
        )
        .limit(1)
    )
    return active_id is not None


def summarize_transition_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a timeline-safe payload summary with PII/secrets redacted."""
    if not isinstance(payload, dict):
        return {}
    return _summarize_mapping(payload, depth=0)


async def list_lead_timeline(
    session: AsyncSession, lead_id: UUID, *, limit: int = 100
) -> list[LeadTimelineEvent]:
    rows = (
        (
            await session.execute(
                select(LeadStateTransition)
                .where(LeadStateTransition.lead_id == lead_id)
                .order_by(LeadStateTransition.created_at.asc())
                .limit(max(1, limit))
            )
        )
        .scalars()
        .all()
    )
    return [_row_to_timeline_event(row, sequence=index + 1) for index, row in enumerate(rows)]


async def list_recent_lead_runs(
    session: AsyncSession, *, limit: int = 20, scan_limit: int | None = None
) -> list[LeadRunSummary]:
    rows = (
        (
            await session.execute(
                select(LeadStateTransition)
                .order_by(LeadStateTransition.created_at.desc())
                .limit(max(limit * 20, scan_limit or limit))
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[tuple[UUID, str | None], list[LeadStateTransition]] = {}
    for row in rows:
        grouped.setdefault((row.lead_id, row.workflow_run_id), []).append(row)

    summaries = [_summarize_run(group) for group in grouped.values()]
    summaries.sort(key=lambda item: item.updated_at, reverse=True)
    return summaries[: max(1, limit)]


def _row_to_timeline_event(row: LeadStateTransition, *, sequence: int) -> LeadTimelineEvent:
    return LeadTimelineEvent(
        id=row.id,
        lead_id=row.lead_id,
        sequence=sequence,
        from_state=row.from_state,
        to_state=row.to_state,
        event_type=row.event_type,
        task_name=row.task_name,
        workflow_run_id=row.workflow_run_id,
        status=row.status,
        created_at=row.created_at,
        payload_summary=summarize_transition_payload(row.payload_json),
    )


def _summarize_run(rows: list[LeadStateTransition]) -> LeadRunSummary:
    ordered = sorted(rows, key=lambda row: row.created_at)
    latest = ordered[-1]
    error_count = sum(
        1
        for row in ordered
        if row.status not in SUCCESS_TRANSITION_STATUSES
        and row.status not in ACTIVE_TRANSITION_STATUSES
    )
    review_count = sum(1 for row in ordered if row.event_type.startswith("admin.review"))
    has_active = any(row.status in ACTIVE_TRANSITION_STATUSES for row in ordered)
    status = "attention" if error_count else "running" if has_active else "succeeded"
    return LeadRunSummary(
        lead_id=latest.lead_id,
        workflow_run_id=latest.workflow_run_id,
        current_state=latest.to_state,
        status=status,
        event_count=len(ordered),
        error_count=error_count,
        review_count=review_count,
        started_at=ordered[0].created_at,
        updated_at=latest.created_at,
        latest_event_type=latest.event_type,
        artifact_paths=_collect_artifact_paths(ordered),
    )


def _collect_artifact_paths(rows: list[LeadStateTransition]) -> list[str]:
    paths: list[str] = []
    for row in rows:
        _collect_artifact_values(summarize_transition_payload(row.payload_json), paths)
    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped[:MAX_TIMELINE_PAYLOAD_ITEMS]


def _collect_artifact_values(value: Any, paths: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(part in str(key).lower() for part in _ARTIFACT_KEY_PARTS):
                _append_artifact_value(item, paths)
            else:
                _collect_artifact_values(item, paths)
    elif isinstance(value, list):
        for item in value:
            _collect_artifact_values(item, paths)


def _append_artifact_value(value: Any, paths: list[str]) -> None:
    if isinstance(value, str):
        paths.append(value)
    elif isinstance(value, list):
        for item in value:
            _append_artifact_value(item, paths)
    elif isinstance(value, dict):
        for item in value.values():
            _append_artifact_value(item, paths)


def _summarize_mapping(mapping: dict[str, Any], *, depth: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for raw_key, value in mapping.items():
        key = str(raw_key)
        normalized_key = key.lower()
        if _is_sensitive_key(normalized_key):
            summary[key] = "[redacted]"
            continue
        summary[key] = _summarize_value(value, key=normalized_key, depth=depth)
    return summary


def _summarize_value(value: Any, *, key: str, depth: int) -> Any:
    if isinstance(value, dict):
        if depth >= 2:
            return {"summary": "nested payload omitted"}
        return _summarize_mapping(value, depth=depth + 1)
    if isinstance(value, list):
        summarized = [
            _summarize_value(item, key=key, depth=depth + 1)
            for item in value[:MAX_TIMELINE_PAYLOAD_ITEMS]
        ]
        omitted = len(value) - len(summarized)
        if omitted > 0:
            summarized.append({"omitted_count": omitted})
        return summarized
    if isinstance(value, str):
        return _summarize_string(value, key=key)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _summarize_string(str(value), key=key)


def _is_sensitive_key(key: str) -> bool:
    return key in _SENSITIVE_EXACT_KEYS or any(part in key for part in _SENSITIVE_KEY_PARTS)


def _summarize_string(value: str, *, key: str) -> str:
    text = _EMAIL_RE.sub("[redacted-email]", value)
    text = _E164_RE.sub("[redacted-phone]", text)
    if key.endswith("_url") or key.endswith("_uri") or key in {"url", "uri"}:
        text = _sanitize_url(text)
    if len(text) > MAX_TIMELINE_STRING_LENGTH:
        text = f"{text[: MAX_TIMELINE_STRING_LENGTH - 3]}..."
    return text


def _sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
