"""hermes_self_evolution workflow: weekly cron.

reads recent agent traces from langfuse, looks for systematic failure
modes, proposes skill / prompt mutations as rows in the
`skill_proposals` postgres table. proposals are reviewed by the
operator before any code change merges.

uses opus via oauth. weekly cadence + bounded analysis budget make
the rate-limit footprint trivial; opus-quality reasoning over the
trace corpus is the differentiator.

reference: NousResearch/hermes-agent-self-evolution (mit). this
implementation is a minimal scaffold; expand the trace-digest +
proposal-persistence logic as the corpus grows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from hatchet_sdk import Context
from stormlead_core import get_logger

from agent_runtime.execution import (
    ModelPolicy,
    TaskPolicy,
    emit_task_event,
    make_envelope,
    run_agent_task,
)

log = get_logger(__name__)


_HERMES_SYSTEM_PROMPT = """\
You are a self-improvement engineer for an agentic lead-gen system.
You will be given a digest of last week's agent traces (qualification
decisions, ping-post outcomes, voice-call transcripts) along with the
current skill / prompt registry.

Output up to 5 proposed changes as a JSON array. Each item:

{
  "skill_name": "<which skill to modify>",
  "mutation_type": "prompt" | "tool_choice" | "parameter",
  "proposed_diff": "<human-readable description of the change>",
  "expected_impact": "<which trace failure modes this addresses>",
  "confidence": <float 0.0..1.0>
}

Be conservative; propose only changes you can defend with cited
traces. The operator reviews proposals before any code change lands.
"""


async def hermes_self_evolution(context: Context) -> dict[str, Any]:
    """weekly cron. trace digest -> opus -> proposals (raw text in v1)."""
    # TODO: pull last-week traces from langfuse api
    # TODO: load current skill / prompt registry from disk
    # TODO: persist proposals to skill_proposals table
    digest = "TODO: populate from langfuse trace digest + skill registry"

    payload = context.workflow_input()
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
            fallback_model="claude-sonnet-4-5",
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

    log.info("hermes.done", proposal_chars=len(proposals_text))
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
    return {"proposals_raw": proposals_text}
