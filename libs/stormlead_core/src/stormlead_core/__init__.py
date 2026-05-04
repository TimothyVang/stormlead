"""stormlead shared core: models, events, filter dsl, observability."""

from stormlead_core.dedup import (
    DuplicateWindow,
    QualityScore,
    build_duplicate_window,
    initial_quality_score,
    normalize_address,
    normalize_phone,
)
from stormlead_core.events import (
    CallEvent,
    LeadCaptured,
    LeadEvent,
    PingPostResult,
    StormDetected,
    StormEvent,
)
from stormlead_core.filters import BuyerFilter, evaluate_filter
from stormlead_core.logging import configure_logging, get_logger
from stormlead_core.models import (
    Buyer,
    BuyerSalesStage,
    BuyerStatus,
    DamageTier,
    Lead,
    LeadClass,
    LeadSource,
    LeadStatus,
    Storm,
    StormSeverity,
)
from stormlead_core.observability import (
    ERROR_SINK,
    bind_correlation_id,
    correlation_scope,
    current_correlation_id,
    emit_event,
    emit_metric,
)
from stormlead_core.pipeline import (
    InvalidPipelineTransitionError,
    PipelineState,
    assert_transition,
    can_transition,
    is_terminal,
    next_states,
)
from stormlead_core.replay import ReplayPlan, build_replay_plan

__all__ = [
    "ERROR_SINK",
    "Buyer",
    "BuyerFilter",
    "BuyerSalesStage",
    "BuyerStatus",
    "CallEvent",
    "DamageTier",
    "DuplicateWindow",
    "InvalidPipelineTransitionError",
    "Lead",
    "LeadCaptured",
    "LeadClass",
    "LeadEvent",
    "LeadSource",
    "LeadStatus",
    "PingPostResult",
    "PipelineState",
    "QualityScore",
    "ReplayPlan",
    "Storm",
    "StormDetected",
    "StormEvent",
    "StormSeverity",
    "assert_transition",
    "bind_correlation_id",
    "build_duplicate_window",
    "build_replay_plan",
    "can_transition",
    "configure_logging",
    "correlation_scope",
    "current_correlation_id",
    "emit_event",
    "emit_metric",
    "evaluate_filter",
    "get_logger",
    "initial_quality_score",
    "is_terminal",
    "next_states",
    "normalize_address",
    "normalize_phone",
]
