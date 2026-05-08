from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import httpx
from stormlead_core import get_logger
from stormlead_core.events import AgentTaskEnvelope, AgentTaskEvent

from agent_runtime.auth import litellm_chat_completions_url, litellm_headers

log = get_logger(__name__)


@dataclass(frozen=True)
class ModelPolicy:
    primary_model: str
    fallback_model: str
    model_tier: Literal["premium", "standard", "economy"]
    token_cap: int
    cost_cap_usd: float


@dataclass(frozen=True)
class TaskPolicy:
    timeout_seconds: int
    retry_count: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    # intentionally conservative static estimates for budget enforcement
    if "opus" in model:
        in_rate, out_rate = 0.000015, 0.000075
    elif "sonnet" in model:
        in_rate, out_rate = 0.000003, 0.000015
    else:
        in_rate, out_rate = 0.000001, 0.000005
    return (input_tokens * in_rate) + (output_tokens * out_rate)


def _completion_payload(
    *,
    model: str,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max(1, max_tokens),
    }


def _extract_completion_text(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LiteLLM response did not include choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("LiteLLM response did not include a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("LiteLLM response message content was not text")
    return content


def emit_task_event(
    *,
    status: Literal["started", "success", "failure", "dead_lettered"],
    event_type: Literal[
        "agent.task.started",
        "agent.task.succeeded",
        "agent.task.failed",
        "agent.task.dead_lettered",
    ],
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
        occurred_at=datetime.now(UTC),
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
        fallback_used = idx > 0
        try:
            if allowed_tools:
                raise ValueError("LiteLLM chat execution does not support agent tools yet")
            async with httpx.AsyncClient(timeout=envelope.timeout_seconds) as client:
                response = await client.post(
                    litellm_chat_completions_url(),
                    headers=litellm_headers(),
                    json=_completion_payload(
                        model=model,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        max_tokens=envelope.token_cap - input_tokens,
                    ),
                )
                response.raise_for_status()
                result_text = _extract_completion_text(response.json())

            out_tokens = _estimate_tokens(result_text)
            total_tokens = input_tokens + out_tokens
            est_cost = _estimate_cost_usd(model, input_tokens, out_tokens)
            if total_tokens > envelope.token_cap:
                raise ValueError(f"total token cap exceeded: {total_tokens} > {envelope.token_cap}")
            if est_cost > envelope.cost_cap_usd:
                raise ValueError(
                    f"cost cap exceeded: ${est_cost:.4f} > ${envelope.cost_cap_usd:.4f}"
                )

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
        model_tier=model_policy.model_tier,
        primary_model=model_policy.primary_model,
        fallback_model=model_policy.fallback_model,
        token_cap=model_policy.token_cap,
        cost_cap_usd=model_policy.cost_cap_usd,
    )
