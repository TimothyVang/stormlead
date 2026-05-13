"""hermes_self_evolution workflow: weekly cron.

reads recent agent traces from langfuse, looks for systematic failure
modes, proposes skill / prompt mutations as rows in the
`skill_proposals` postgres table. proposals are reviewed by the
operator before any code change merges.

All model calls route through LiteLLM so tracing, keys, and budgets stay centralized.

reference: NousResearch/hermes-agent-self-evolution (mit). this
implementation is a minimal scaffold; expand the trace-digest +
proposal-persistence logic as the corpus grows.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from hatchet_sdk import Context
from stormlead_core import get_logger
from stormlead_db import LearningProposal, SkillProposalRow, get_session

from agent_runtime.execution import (
    ModelPolicy,
    TaskPolicy,
    emit_task_event,
    make_envelope,
    run_agent_task,
)

log = get_logger(__name__)

_SKILL_PROPOSAL_TYPES = {"prompt_update", "new_skill", "retire_skill"}
_LEARNING_PROPOSAL_TYPES = {"scoring_threshold", "cadence_change", "prompt_update"}


_HERMES_SYSTEM_PROMPT = """\
You are a self-improvement engineer for an agentic lead-gen system.
You will be given a digest of last week's agent traces (qualification
decisions, ping-post outcomes, voice-call transcripts) along with the
current skill / prompt registry.

Output up to 5 proposed changes as a JSON array. Each item:

{
  "target_area": "<scoring, cadence, prompt, or skill area>",
  "skill_name": "<which skill to modify, when relevant>",
  "proposal_type": "scoring_threshold" | "cadence_change" | "prompt_update" | "new_skill" | "retire_skill",
  "title": "<short operator-facing title>",
  "rationale": "<which trace failure modes this addresses>",
  "confidence": <float 0.0..1.0>
}

Be conservative; propose only changes you can defend with cited
traces. The operator reviews proposals before any code change lands.
"""


async def _fetch_weekly_traces() -> list[dict[str, Any]]:
    host = os.getenv("LANGFUSE_HOST", "").rstrip("/")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not host or not secret_key:
        return []

    from_ts = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{host}/api/public/traces",
                params={"fromTimestamp": from_ts, "limit": 100, "orderBy": "timestamp.desc"},
                headers={"Authorization": f"Bearer {secret_key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        log.warning("hermes.langfuse_fetch_failed", error=str(exc))
        return []

    data = payload.get("data", []) if isinstance(payload, dict) else []
    return data if isinstance(data, list) else []


def _summarize_traces(traces: list[dict[str, Any]]) -> str:
    failures = 0
    for trace in traces:
        status = str(trace.get("status") or trace.get("level") or "").lower()
        if status in {"error", "failed", "failure"}:
            failures += 1
    return f"Traces analyzed: {len(traces)}\nFailure-like traces: {failures}"


def _load_skill_registry(skills_dir: Path | None = None) -> list[dict[str, Any]]:
    root = skills_dir or Path("skills")
    registry: list[dict[str, Any]] = []
    if not root.exists():
        return registry

    for path in sorted(root.glob("*.jsonl")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    item.setdefault("source_file", str(path))
                    registry.append(item)
        except Exception as exc:
            log.warning("hermes.skill_registry_load_failed", path=str(path), error=str(exc))
    return registry


def _coerce_proposal_type(value: Any) -> str | None:
    proposal_type = str(value or "").strip()
    if proposal_type in _SKILL_PROPOSAL_TYPES | _LEARNING_PROPOSAL_TYPES:
        return proposal_type
    if proposal_type in {"prompt", "tool_choice", "parameter"}:
        return "prompt_update"
    if proposal_type in {"threshold", "scoring", "score_threshold"}:
        return "scoring_threshold"
    if proposal_type in {"cadence", "schedule", "frequency"}:
        return "cadence_change"
    return None


def _learning_target_area(item: dict[str, Any]) -> str:
    target = item.get("target_area") or item.get("skill_name") or item.get("metric")
    return str(target or item.get("proposal_type") or "agent_policy")[:64]


def _parse_proposals(proposals_text: str) -> list[dict[str, Any]]:
    payload = json.loads(proposals_text)
    if isinstance(payload, dict):
        payload = payload.get("proposals", [])
    if not isinstance(payload, list):
        return []

    proposals: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        proposal_type = _coerce_proposal_type(
            item.get("proposal_type") or item.get("mutation_type")
        )
        if proposal_type is None:
            continue
        title = str(
            item.get("title")
            or item.get("proposed_diff")
            or item.get("skill_name")
            or "Hermes proposal"
        )[:255]
        proposals.append({**item, "proposal_type": proposal_type, "title": title})
    return proposals


async def _persist_proposals(proposals: str | list[dict[str, Any]], proposal_date: date) -> int:
    if isinstance(proposals, str):
        try:
            parsed = _parse_proposals(proposals)
        except Exception as exc:
            log.warning("hermes.proposal_parse_failed", error=str(exc))
            return 0
    else:
        parsed = proposals

    rows = parsed[:5]
    if not rows:
        return 0

    async with get_session() as session:
        for item in rows:
            proposal_type = str(item["proposal_type"])
            title = str(item.get("title") or "Hermes proposal")[:255]
            rationale = item.get("rationale") or item.get("expected_impact")
            skill_row_id: UUID | None = None
            if proposal_type in _SKILL_PROPOSAL_TYPES:
                skill_row_id = uuid4()
                session.add(
                    SkillProposalRow(
                        id=skill_row_id,
                        proposal_date=proposal_date,
                        proposal_type=proposal_type,
                        skill_name=item.get("skill_name"),
                        title=title,
                        rationale=rationale,
                        proposal_json=item,
                        status="pending_review",
                    )
                )
            if proposal_type in _LEARNING_PROPOSAL_TYPES:
                session.add(
                    LearningProposal(
                        source_proposal_id=skill_row_id,
                        proposal_date=proposal_date,
                        proposal_type=proposal_type,
                        target_area=_learning_target_area(item),
                        title=title,
                        rationale=rationale,
                        proposal_json=item,
                        status="pending_replay",
                        canary_percent=0,
                        approval_required=True,
                    )
                )
    return len(rows)


async def hermes_self_evolution(context: Context) -> dict[str, Any]:
    """Weekly trace digest -> model proposals -> pending review rows."""
    traces = await _fetch_weekly_traces()
    trace_summary = _summarize_traces(traces)
    skill_registry = _load_skill_registry()
    digest = "\n\n".join(
        [
            trace_summary,
            "Skill registry:",
            json.dumps(skill_registry[:50], default=str),
        ]
    )

    workflow_input = context.workflow_input
    payload = workflow_input() if callable(workflow_input) else workflow_input
    correlation_id = None
    if isinstance(payload.get("correlation_id"), str):
        correlation_id = UUID(payload["correlation_id"])
    envelope = make_envelope(
        task_name="hermes_self_evolution",
        workflow_name="HermesSelfEvolution",
        run_id=str(payload.get("run_id") or uuid4()),
        input_payload=payload,
        correlation_id=correlation_id,
        task_policy=TaskPolicy(timeout_seconds=600, retry_count=1),
        model_policy=ModelPolicy(
            primary_model="claude-opus-4-7",
            fallback_model="claude-sonnet-4-6",
            model_tier="premium",
            token_cap=20_000,
            cost_cap_usd=3.00,
        ),
    )
    emit_task_event(
        status="started",
        event_type="agent.task.started",
        envelope=envelope,
        attempt=1,
        model_used=envelope.primary_model,
        fallback_used=False,
    )

    try:
        proposals_text, usage = await run_agent_task(
            envelope=envelope,
            system_prompt=_HERMES_SYSTEM_PROMPT,
            prompt=digest,
            allowed_tools=[],
        )
    except Exception as exc:
        emit_task_event(
            status="dead_lettered",
            event_type="agent.task.dead_lettered",
            envelope=envelope,
            attempt=envelope.retry_count + 1,
            model_used=envelope.fallback_model or envelope.primary_model,
            fallback_used=True,
            error=str(exc),
        )
        raise

    saved_count = await _persist_proposals(proposals_text, date.today())
    log.info("hermes.done", proposal_chars=len(proposals_text), proposals_saved=saved_count)
    emit_task_event(
        status="success",
        event_type="agent.task.succeeded",
        envelope=envelope,
        attempt=1,
        model_used=str(usage["model_used"]),
        fallback_used=bool(usage["fallback_used"]),
        duration_ms=int(usage["duration_ms"]),
        estimated_input_tokens=int(usage["estimated_input_tokens"]),
        estimated_output_tokens=int(usage["estimated_output_tokens"]),
        estimated_cost_usd=float(usage["estimated_cost_usd"]),
    )
    return {"proposals_raw": proposals_text, "proposals_saved": saved_count}
