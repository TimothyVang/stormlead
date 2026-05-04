"""auth backends for claude-agent-sdk calls.

two paths per docs/research/2026-05-agent-auth-patterns.md:

  oauth   — CLAUDE_CODE_OAUTH_TOKEN, claude.ai pro/max subscription billing,
            opus default. the agent sdk shells out to the claude-code cli
            (installed in this image), which honors the oauth token directly.
            ANTHROPIC_BASE_URL is unset on this path so the cli talks to
            anthropic, not litellm.

  litellm — ANTHROPIC_BASE_URL=http://litellm:4000, virtual api key,
            haiku default. full langfuse tracing + per-route budget caps.

caller picks the backend by workload classification:
  hermes              → oauth/opus
  qualify_complex     → oauth/opus
  qualify_bulk (future) → litellm/haiku
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from claude_agent_sdk import ClaudeAgentOptions

Workload = Literal["hermes", "qualify_complex", "qualify_bulk"]


@dataclass(frozen=True)
class _Backend:
    name: str
    model: str


_OAUTH_OPUS = _Backend(name="oauth_opus", model="claude-opus-4-7")
_LITELLM_HAIKU = _Backend(name="litellm_haiku", model="agent-default")


def _backend_for(workload: Workload) -> _Backend:
    if workload in ("hermes", "qualify_complex"):
        return _OAUTH_OPUS
    return _LITELLM_HAIKU


def get_agent_options(
    workload: Workload,
    *,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> ClaudeAgentOptions:
    """build claude-agent-sdk options for the given workload.

    side effect: mutates os.environ['ANTHROPIC_BASE_URL'] so the sdk + cli
    target the right endpoint. acceptable here because the worker's two
    flows don't interleave at sub-call granularity (one workflow run at a
    time per worker slot).
    """
    backend = _backend_for(workload)
    if backend is _OAUTH_OPUS:
        # oauth path: claude-code cli reads CLAUDE_CODE_OAUTH_TOKEN and
        # talks to anthropic directly. don't go through litellm.
        os.environ.pop("ANTHROPIC_BASE_URL", None)
    else:
        # litellm path: route through the proxy with the virtual api key
        os.environ["ANTHROPIC_BASE_URL"] = os.environ.get(
            "LITELLM_PROXY_URL", "http://litellm:4000"
        )
    kwargs = dict(
        model=model or backend.model,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools or [],
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ClaudeAgentOptions(**kwargs)
