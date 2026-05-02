"""buyer filter dsl using cel (common expression language).

each buyer has a `filter_expression` like:
    lead.state in ['FL','GA','SC'] && lead.damage_tier in ['tier_3_on_structure','tier_2_down_ground'] && lead.property_avm > 250000

we evaluate this server-side against a normalized lead context.
celpy is the pure-python cel implementation. it's safe to evaluate untrusted
expressions because cel has no loops, no side effects, no unbounded compute.

NEVER use eval() / exec() for buyer rules. cel is the explicit-by-design choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import celpy
import structlog

from stormlead_core.models import Lead

log = structlog.get_logger(__name__)


@dataclass
class FilterResult:
    matches: bool
    error: str | None = None


@dataclass
class BuyerFilter:
    expression: str
    program: celpy.Runner

    @classmethod
    def compile(cls, expression: str) -> BuyerFilter:
        env = celpy.Environment()
        ast = env.compile(expression)
        program = env.program(ast)
        return cls(expression=expression, program=program)


def _lead_to_cel(lead: Lead) -> dict[str, Any]:
    """flatten a lead into the variable namespace cel sees."""
    return {
        "lead": {
            "state": lead.state,
            "city": lead.city,
            "zip": lead.zip,
            "damage_tier": lead.damage_tier.value if lead.damage_tier else "",
            "qualification_score": float(lead.qualification_score or 0.0),
            "property_avm": float(lead.property_avm or 0),
            "year_built": int(lead.year_built or 0),
            "owner_occupied": bool(lead.owner_occupied),
            "source": lead.source.value,
        }
    }


def evaluate_filter(expression: str, lead: Lead) -> FilterResult:
    """evaluate a buyer's cel expression against a lead.

    returns matches=False on any error so a broken filter cannot accidentally
    match every lead. log + alert on errors so we can fix the buyer config.
    """
    try:
        f = BuyerFilter.compile(expression)
        result = f.program.evaluate(celpy.json_to_cel(_lead_to_cel(lead)))
        return FilterResult(matches=bool(result))
    except celpy.CELParseError as e:
        log.error("cel.parse_error", expression=expression, error=str(e))
        return FilterResult(matches=False, error=f"parse_error: {e}")
    except celpy.CELEvalError as e:
        log.error("cel.eval_error", expression=expression, error=str(e))
        return FilterResult(matches=False, error=f"eval_error: {e}")
    except Exception as e:  # noqa: BLE001
        log.exception("cel.unexpected_error", expression=expression)
        return FilterResult(matches=False, error=f"unexpected: {e}")
