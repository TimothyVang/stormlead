from __future__ import annotations

from stormlead_db import AgentRunRow, get_session


async def record_run(
    *,
    flow_name: str,
    workload: str,
    model: str,
    max_tokens: int,
    retries: int,
    latency_ms: int,
    estimated_cost_usd: float,
    outcome: str,
    error: str | None = None,
) -> None:
    async with get_session() as s:
        s.add(
            AgentRunRow(
                flow_name=flow_name,
                workload=workload,
                model=model,
                max_tokens=max_tokens,
                retries=retries,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                outcome=outcome,
                error=error,
            )
        )
