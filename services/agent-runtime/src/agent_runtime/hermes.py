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

from claude_agent_sdk import query
from hatchet_sdk import Context
from stormlead_core import get_logger

from agent_runtime.auth import get_agent_options

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

    options = get_agent_options(
        "hermes",
        system_prompt=_HERMES_SYSTEM_PROMPT,
        allowed_tools=[],
    )

    proposals_text = ""
    async for message in query(prompt=digest, options=options):
        content = getattr(message, "content", None)
        if content:
            proposals_text += str(content)

    log.info("hermes.done", proposal_chars=len(proposals_text))
    return {"proposals_raw": proposals_text}
