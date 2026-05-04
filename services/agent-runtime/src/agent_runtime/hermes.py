from __future__ import annotations

from typing import Any

from claude_agent_sdk import query
from hatchet_sdk import Context
from stormlead_core import get_logger

from agent_runtime.auth import get_agent_options
from agent_runtime.policy import Timer, flow_enabled, get_policy
from agent_runtime.telemetry import record_run

log = get_logger(__name__)

_HERMES_SYSTEM_PROMPT = """You are a self-improvement engineer for an agentic lead-gen system."""


async def hermes_self_evolution(context: Context) -> dict[str, Any]:
    if not flow_enabled("hermes"):
        return {"skipped": True, "reason": "hermes flow disabled"}
    digest = "TODO: populate from langfuse trace digest + skill registry"
    policy = get_policy("hermes")
    proposals_text = ""
    outcome = "success"
    err_msg = None
    with Timer() as timer:
        for attempt in range(policy.retries + 1):
            try:
                options = get_agent_options(
                    "hermes",
                    system_prompt=_HERMES_SYSTEM_PROMPT,
                    allowed_tools=[],
                    model=policy.model if attempt == 0 else (policy.fallback_model or policy.model),
                    max_tokens=policy.max_tokens,
                )
                async for message in query(prompt=digest, options=options):
                    content = getattr(message, "content", None)
                    if content:
                        proposals_text += str(content)
                break
            except Exception as exc:
                outcome = "failed"
                err_msg = str(exc)
                if attempt >= policy.retries:
                    raise

    await record_run(
        flow_name="hermes",
        workload="hermes",
        model=policy.model,
        max_tokens=policy.max_tokens,
        retries=policy.retries,
        latency_ms=timer.elapsed_ms,
        estimated_cost_usd=0.0,
        outcome=outcome,
        error=err_msg,
    )
    log.info("hermes.done", proposal_chars=len(proposals_text), latency_ms=timer.elapsed_ms)
    return {"proposals_raw": proposals_text}
