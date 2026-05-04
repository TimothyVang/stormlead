from __future__ import annotations

import os
from dataclasses import dataclass

from agent_runtime.config import disabled_flows
from time import perf_counter


@dataclass(frozen=True)
class InvocationPolicy:
    workload: str
    model: str
    max_tokens: int
    timeout_seconds: int
    retries: int
    fallback_model: str | None


_POLICY = {
    "qualify_complex": InvocationPolicy(
        workload="qualify_complex",
        model="claude-sonnet-4-5",
        max_tokens=1400,
        timeout_seconds=45,
        retries=1,
        fallback_model="claude-haiku-4-5",
    ),
    "hermes": InvocationPolicy(
        workload="hermes",
        model="claude-opus-4-7",
        max_tokens=2800,
        timeout_seconds=180,
        retries=1,
        fallback_model="claude-sonnet-4-5",
    ),
}


def get_policy(workload: str, *, escalate: bool = False) -> InvocationPolicy:
    policy = _POLICY[workload]
    if not escalate:
        return policy
    premium = os.getenv("AGENT_POLICY_PREMIUM_MODEL")
    if premium:
        return InvocationPolicy(**{**policy.__dict__, "model": premium})
    return policy


def flow_enabled(flow_name: str) -> bool:
    return flow_name.lower() not in disabled_flows()


class Timer:
    def __enter__(self) -> "Timer":
        self.t0 = perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.elapsed_ms = int((perf_counter() - self.t0) * 1000)
