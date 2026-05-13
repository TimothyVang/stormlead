from __future__ import annotations

from typing import Any, cast

from stormlead_db import (
    BillingEvent,
    BudgetActionLog,
    CampaignRow,
    CampaignSpendSnapshot,
    ChannelSuppression,
    ConsentAudit,
    ExceptionQueueItem,
    LeadRow,
    LearningProposal,
    OutreachAttempt,
    PaymentCustomer,
    PaymentWebhookEvent,
    TrackingLink,
    WalletAutorefillRule,
)


def test_lead_model_has_resale_dedup_columns() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "normalized_address" in columns
    assert "is_resale" in columns


def test_lead_model_has_capture_idempotency_columns() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "capture_webhook_id" in columns
    assert "capture_event_emitted_at" in columns
    assert "capture_event_status" in columns
    assert "capture_event_claimed_at" in columns


def test_lead_model_has_location_photo_metadata_columns() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "google_click_id" in columns
    assert "gps_latitude" in columns
    assert "gps_longitude" in columns
    assert "gps_accuracy_meters" in columns
    assert "gps_captured_at" in columns
    assert "location_source" in columns
    assert "location_confirmed_at" in columns
    assert "location_verification_status" in columns


def test_lead_model_has_tree_damage_intake_columns() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "damage_type" in columns
    assert "urgency" in columns
    assert "safety_flags" in columns


def test_lead_model_has_structured_damage_review_columns() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "damage_summary" in columns
    assert "visible_risk_level" in columns
    assert "estimated_job_size" in columns
    assert "buyer_notes" in columns


def test_lead_model_has_consent_version_column() -> None:
    columns = set(LeadRow.__table__.columns.keys())
    assert "consent_version" in columns


def test_consent_audit_model_has_consent_version_column() -> None:
    columns = set(ConsentAudit.__table__.columns.keys())
    assert "consent_version" in columns


def test_lead_model_declares_sellable_resale_unique_index() -> None:
    table = cast(Any, LeadRow.__table__)
    names = {index.name for index in table.indexes}
    assert "uq_lead_phone_address_storm_sellable" in names


def test_lead_model_declares_capture_webhook_unique_index() -> None:
    table = cast(Any, LeadRow.__table__)
    indexes = {index.name: index for index in table.indexes}
    capture_index = indexes["uq_leads_capture_webhook_id"]
    assert capture_index.unique is True
    assert [column.name for column in capture_index.columns] == ["capture_webhook_id"]


def test_lead_model_declares_location_metadata_indexes() -> None:
    table = cast(Any, LeadRow.__table__)
    names = {index.name for index in table.indexes}
    assert "ix_leads_google_click_id" in names
    assert "ix_leads_location_verification_status" in names
    assert "ix_leads_damage_type" in names
    assert "ix_leads_urgency" in names
    assert "ix_leads_visible_risk_level" in names
    assert "ix_leads_estimated_job_size" in names


def test_billing_event_has_external_event_id_unique_index() -> None:
    columns = set(BillingEvent.__table__.columns.keys())
    assert "external_event_id" in columns
    table = cast(Any, BillingEvent.__table__)
    names = {index.name for index in table.indexes}
    assert "uq_billing_events_external_event_id" in names


def test_payment_webhook_event_declares_idempotency_contract() -> None:
    columns = set(PaymentWebhookEvent.__table__.columns.keys())
    assert {
        "provider",
        "external_event_id",
        "event_type",
        "status",
        "payload_sha256",
        "payload_json",
    }.issubset(columns)
    table = cast(Any, PaymentWebhookEvent.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    assert "uq_payment_webhook_events_provider_external_event_id" in constraints
    assert "ck_payment_webhook_events_status" in constraints


def test_payment_customer_declares_provider_customer_contract() -> None:
    columns = set(PaymentCustomer.__table__.columns.keys())
    assert {"buyer_id", "provider", "external_customer_id", "status", "metadata_json"}.issubset(
        columns
    )
    table = cast(Any, PaymentCustomer.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    assert "uq_payment_customers_buyer_provider" in constraints
    assert "uq_payment_customers_provider_external_customer_id" in constraints
    assert "ck_payment_customers_status" in constraints


def test_wallet_autorefill_rule_declares_disabled_by_default_contract() -> None:
    columns = set(WalletAutorefillRule.__table__.columns.keys())
    assert {
        "buyer_id",
        "provider",
        "status",
        "threshold_cents",
        "refill_amount_cents",
        "daily_cap_cents",
        "monthly_cap_cents",
    }.issubset(columns)
    table = cast(Any, WalletAutorefillRule.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    assert "uq_wallet_autorefill_rules_buyer_provider" in constraints
    assert "ck_wallet_autorefill_rules_status" in constraints
    assert "ck_wallet_autorefill_rules_refill_amount" in constraints


def test_outreach_attempt_declares_provider_neutral_contract() -> None:
    columns = set(OutreachAttempt.__table__.columns.keys())
    assert {
        "lead_id",
        "buyer_id",
        "channel",
        "direction",
        "provider",
        "external_message_id",
        "idempotency_key",
        "status",
        "payload_json",
    }.issubset(columns)
    table = cast(Any, OutreachAttempt.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}
    assert "ck_outreach_attempts_channel" in constraints
    assert "ck_outreach_attempts_direction" in constraints
    assert "ck_outreach_attempts_status" in constraints
    assert "ck_outreach_attempts_queued_has_idempotency" in constraints
    assert "uq_outreach_attempts_idempotency_key" in indexes
    assert "uq_outreach_attempts_provider_message" in indexes
    assert "ix_outreach_attempts_lead_created_at" in indexes
    status_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_outreach_attempts_status"
    )
    assert "recorded" in str(status_constraint.sqltext)
    assert "received" in str(status_constraint.sqltext)
    assert table.columns["status"].default.arg == "recorded"
    assert table.columns["provider"].nullable is True
    assert table.columns["external_message_id"].nullable is True
    provider_message_index = indexes["uq_outreach_attempts_provider_message"]
    provider_message_predicate = provider_message_index.dialect_options["postgresql"]["where"]
    assert provider_message_index.unique is True
    assert "provider IS NOT NULL" in str(provider_message_predicate)
    assert "external_message_id IS NOT NULL" in str(provider_message_predicate)


def test_channel_suppression_declares_opt_out_contract() -> None:
    columns = set(ChannelSuppression.__table__.columns.keys())
    assert {
        "channel",
        "phone_e164",
        "email",
        "status",
        "reason",
        "source_provider",
        "external_event_id",
        "payload_json",
    }.issubset(columns)
    table = cast(Any, ChannelSuppression.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}
    assert "ck_channel_suppressions_channel" in constraints
    assert "ck_channel_suppressions_status" in constraints
    assert "ck_channel_suppressions_contact_present" in constraints
    assert "ck_channel_suppressions_channel_contact_match" in constraints
    assert "uq_channel_suppressions_active_phone" in indexes
    assert "uq_channel_suppressions_active_email" in indexes
    assert "uq_channel_suppressions_provider_event" in indexes
    contact_match = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_channel_suppressions_channel_contact_match"
    )
    assert "phone_e164 IS NOT NULL" in str(contact_match.sqltext)
    assert "email IS NOT NULL" in str(contact_match.sqltext)
    provider_event_index = indexes["uq_channel_suppressions_provider_event"]
    provider_event_predicate = provider_event_index.dialect_options["postgresql"]["where"]
    assert provider_event_index.unique is True
    assert "source_provider IS NOT NULL" in str(provider_event_predicate)
    assert "external_event_id IS NOT NULL" in str(provider_event_predicate)
    assert table.columns["phone_e164"].nullable is True
    assert table.columns["email"].nullable is True


def test_exception_queue_item_declares_owner_sla_contract() -> None:
    columns = set(ExceptionQueueItem.__table__.columns.keys())
    assert {
        "kind",
        "severity",
        "status",
        "owner",
        "entity_type",
        "lead_id",
        "buyer_id",
        "return_request_id",
        "post_result_id",
        "reason",
        "recommended_action",
        "idempotency_key",
        "sla_due_at",
        "payload_json",
        "resolved_at",
    }.issubset(columns)
    table = cast(Any, ExceptionQueueItem.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}
    assert "ck_exception_queue_severity" in constraints
    assert "ck_exception_queue_status" in constraints
    assert "uq_exception_queue_idempotency_key" in indexes
    assert "ix_exception_queue_status_severity_sla" in indexes
    assert table.columns["status"].default.arg == "open"
    assert table.columns["owner"].nullable is True
    idempotency_index = indexes["uq_exception_queue_idempotency_key"]
    assert idempotency_index.unique is True
    assert "idempotency_key IS NOT NULL" in str(
        idempotency_index.dialect_options["postgresql"]["where"]
    )


def test_campaign_spend_registry_declares_platform_idempotency_contract() -> None:
    campaign_columns = set(CampaignRow.__table__.columns.keys())
    assert {
        "platform",
        "external_campaign_id",
        "name",
        "status",
        "service",
        "market_state",
        "target_zips",
        "daily_budget_cents",
        "metadata_json",
    }.issubset(campaign_columns)
    campaign_table = cast(Any, CampaignRow.__table__)
    campaign_constraints = {constraint.name for constraint in campaign_table.constraints}
    assert "uq_campaigns_platform_external_campaign_id" in campaign_constraints
    assert "ck_campaigns_platform" in campaign_constraints
    assert "ck_campaigns_status" in campaign_constraints

    spend_columns = set(CampaignSpendSnapshot.__table__.columns.keys())
    assert {
        "campaign_id",
        "platform",
        "external_campaign_id",
        "snapshot_date",
        "spend_cents",
        "clicks",
        "impressions",
        "conversions",
        "payload_json",
    }.issubset(spend_columns)
    spend_table = cast(Any, CampaignSpendSnapshot.__table__)
    spend_constraints = {constraint.name for constraint in spend_table.constraints}
    spend_indexes = {index.name for index in spend_table.indexes}
    assert "uq_campaign_spend_platform_campaign_date" in spend_constraints
    assert "ck_campaign_spend_nonnegative" in spend_constraints
    assert "ix_campaign_spend_campaign_date" in spend_indexes

    tracking_columns = set(TrackingLink.__table__.columns.keys())
    assert {
        "campaign_id",
        "source",
        "medium",
        "campaign_slug",
        "destination_url",
        "tracking_url",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "click_id_param",
    }.issubset(tracking_columns)
    tracking_table = cast(Any, TrackingLink.__table__)
    tracking_constraints = {constraint.name for constraint in tracking_table.constraints}
    tracking_indexes = {index.name for index in tracking_table.indexes}
    assert "uq_tracking_links_tracking_url" in tracking_constraints
    assert "ck_tracking_links_status" in tracking_constraints
    assert "ix_tracking_links_campaign_status" in tracking_indexes


def test_budget_action_log_declares_pacing_audit_contract() -> None:
    columns = set(BudgetActionLog.__table__.columns.keys())
    assert {
        "campaign_id",
        "platform",
        "external_campaign_id",
        "action",
        "status",
        "approval_required",
        "reason",
        "idempotency_key",
        "metrics_json",
        "decision_json",
    }.issubset(columns)
    table = cast(Any, BudgetActionLog.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}
    assert "ck_budget_action_logs_action" in constraints
    assert "ck_budget_action_logs_status" in constraints
    assert "uq_budget_action_logs_idempotency_key" in indexes
    assert "ix_budget_action_logs_campaign_created" in indexes
    assert table.columns["status"].default.arg == "planned"
    assert table.columns["approval_required"].default.arg is False
    action_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_budget_action_logs_action"
    )
    status_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_budget_action_logs_status"
    )
    assert "auto_pause" in str(action_constraint.sqltext)
    assert "propose_increase" in str(action_constraint.sqltext)
    assert "block_increase" in str(action_constraint.sqltext)
    assert "approval_required" in str(status_constraint.sqltext)
    idempotency_index = indexes["uq_budget_action_logs_idempotency_key"]
    assert idempotency_index.unique is True
    assert "idempotency_key IS NOT NULL" in str(
        idempotency_index.dialect_options["postgresql"]["where"]
    )


def test_learning_proposal_declares_canary_guardrail_contract() -> None:
    columns = set(LearningProposal.__table__.columns.keys())
    assert {
        "source_proposal_id",
        "proposal_date",
        "proposal_type",
        "target_area",
        "status",
        "canary_percent",
        "guardrail_metric",
        "baseline_value",
        "candidate_value",
        "rollback_threshold_pct",
        "approval_required",
        "idempotency_key",
        "proposal_json",
        "replay_result_json",
        "rollback_reason",
    }.issubset(columns)
    table = cast(Any, LearningProposal.__table__)
    constraints = {constraint.name for constraint in table.constraints}
    indexes = {index.name: index for index in table.indexes}
    assert "ck_learning_proposals_type" in constraints
    assert "ck_learning_proposals_status" in constraints
    assert "ck_learning_proposals_canary_percent" in constraints
    assert "uq_learning_proposals_idempotency_key" in indexes
    assert "ix_learning_proposals_status_created" in indexes
    assert "ix_learning_proposals_source_status" in indexes
    assert table.columns["status"].default.arg == "pending_replay"
    assert table.columns["canary_percent"].default.arg == 0
    assert table.columns["guardrail_metric"].default.arg == "conversion_rate"
    assert table.columns["approval_required"].default.arg is True

    proposal_type_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_learning_proposals_type"
    )
    status_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_learning_proposals_status"
    )
    assert "scoring_threshold" in str(proposal_type_constraint.sqltext)
    assert "cadence_change" in str(proposal_type_constraint.sqltext)
    assert "canary_active" in str(status_constraint.sqltext)
    assert "rollback_triggered" in str(status_constraint.sqltext)
    assert "pending_approval" in str(status_constraint.sqltext)
    idempotency_index = indexes["uq_learning_proposals_idempotency_key"]
    assert idempotency_index.unique is True
    assert "idempotency_key IS NOT NULL" in str(
        idempotency_index.dialect_options["postgresql"]["where"]
    )
