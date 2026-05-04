from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from stormlead_core import get_logger
from stormlead_core.events import AgentRunEvent, AgentTaskEnvelope, AgentTaskEvent

log = get_logger(__name__)


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELED},
    RunStatus.RUNNING: {
        RunStatus.AWAITING_APPROVAL,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELED,
    },
    RunStatus.AWAITING_APPROVAL: {RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.CANCELED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELED: set(),
}


@dataclass(frozen=True)
class ModelPolicy:
    primary_model: str
    fallback_model: str
    model_tier: str
    token_cap: int
    cost_cap_usd: float


@dataclass(frozen=True)
class TaskPolicy:
    timeout_seconds: int
    retry_count: int


@dataclass
class RunStateMachine:
    run_id: str
    lead_id: UUID | None
    correlation_id: UUID | None
    status: RunStatus = RunStatus.QUEUED
    attempt: int = 1

    def transition(self, next_status: RunStatus, *, reason: str | None = None) -> AgentRunEvent:
        if next_status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid transition: {self.status} -> {next_status}")
        self.status = next_status
        event_type = {
            RunStatus.RUNNING: "run.started",
            RunStatus.AWAITING_APPROVAL: "run.awaiting_approval",
            RunStatus.COMPLETED: "run.completed",
            RunStatus.FAILED: "run.failed",
            RunStatus.CANCELED: "run.canceled",
        }.get(next_status, "run.started")
        return AgentRunEvent(
            event_id=uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            correlation_id=self.correlation_id,
            run_id=self.run_id,
            lead_id=self.lead_id,
            status=self.status,
            attempt=self.attempt,
            reason=reason,
        )


def emit_run_event(event: AgentRunEvent) -> None:
    log.info("agent.run.event", **event.model_dump(mode="json"))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if "opus" in model:
        in_rate, out_rate = 0.000015, 0.000075
    elif "sonnet" in model:
        in_rate, out_rate = 0.000003, 0.000015
    else:
        in_rate, out_rate = 0.000001, 0.000005
    return (input_tokens * in_rate) + (output_tokens * out_rate)


def emit_task_event(
    *,
    status: str,
    event_type: str,
    envelope: AgentTaskEnvelope,
    attempt: int,
    model_used: str,
    fallback_used: bool,
    duration_ms: int | None = None,
    error: str | None = None,
    estimated_input_tokens: int | None = None,
    estimated_output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
) -> None:
    event = AgentTaskEvent(
        event_id=uuid4(),
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        correlation_id=envelope.correlation_id,
        task=envelope,
        status=status,
        attempt=attempt,
        model_used=model_used,
        fallback_used=fallback_used,
        duration_ms=duration_ms,
        error=error,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
    log.info("agent.task.event", **event.model_dump(mode="json"))


async def run_agent_task(
    *,
    envelope: AgentTaskEnvelope,
    system_prompt: str,
    prompt: str,
    allowed_tools: list[str],
) -> tuple[str, dict[str, float | int | str | bool]]:
    input_tokens = _estimate_tokens(prompt)
    if input_tokens > envelope.token_cap:
        raise ValueError(f"input token cap exceeded: {input_tokens} > {envelope.token_cap}")

    models = [envelope.primary_model]
    if envelope.fallback_model:
        models.append(envelope.fallback_model)

    start = time.perf_counter()
    last_err: Exception | None = None
    for idx, model in enumerate(models):
        from claude_agent_sdk import ClaudeAgentOptions, query

        fallback_used = idx > 0
        options = ClaudeAgentOptions(model=model, system_prompt=system_prompt, allowed_tools=allowed_tools)
        try:
            result_text = ""
            async for message in query(prompt=prompt, options=options):
                content = getattr(message, "content", None)
                if content:
                    result_text += str(content)

            out_tokens = _estimate_tokens(result_text)
            total_tokens = input_tokens + out_tokens
            est_cost = _estimate_cost_usd(model, input_tokens, out_tokens)
            if total_tokens > envelope.token_cap:
                raise ValueError(f"total token cap exceeded: {total_tokens} > {envelope.token_cap}")
            if est_cost > envelope.cost_cap_usd:
                raise ValueError(f"cost cap exceeded: ${est_cost:.4f} > ${envelope.cost_cap_usd:.4f}")

            duration_ms = int((time.perf_counter() - start) * 1000)
            return result_text, {
                "duration_ms": duration_ms,
                "estimated_input_tokens": input_tokens,
                "estimated_output_tokens": out_tokens,
                "estimated_cost_usd": est_cost,
                "model_used": model,
                "fallback_used": fallback_used,
            }
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"all model attempts failed: {last_err}") from last_err


def make_envelope(
    *,
    task_name: str,
    workflow_name: str,
    run_id: str,
    input_payload: dict,
    correlation_id: UUID | None,
    task_policy: TaskPolicy,
    model_policy: ModelPolicy,
) -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        task_name=task_name,
        workflow_name=workflow_name,
        run_id=run_id,
        input_payload=input_payload,
        correlation_id=correlation_id,
        timeout_seconds=task_policy.timeout_seconds,
        retry_count=task_policy.retry_count,
        model_tier=model_policy.model_tier,  # type: ignore[arg-type]
        primary_model=model_policy.primary_model,
        fallback_model=model_policy.fallback_model,
        token_cap=model_policy.token_cap,
        cost_cap_usd=model_policy.cost_cap_usd,
    )
