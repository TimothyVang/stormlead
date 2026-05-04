from __future__ import annotations

import os


def disabled_flows() -> set[str]:
    return {x.strip().lower() for x in os.getenv("AGENT_FLOWS_DISABLED", "").split(",") if x.strip()}


def daily_budget_usd() -> float:
    return float(os.getenv("AGENT_DAILY_BUDGET_USD", "150"))
