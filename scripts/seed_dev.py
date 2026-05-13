"""seed dev postgres with one storm + two buyers + one lead.

idempotent — fixed UUIDs + ON CONFLICT (id) DO NOTHING. safe to re-run.
intended for local dev + the smoke_e2e harness; never run against prod.

usage: uv run python scripts/seed_dev.py
optional: STORMLEAD_LOCAL_BUYER_WEBHOOK_BASE=http://host.docker.internal:<port>
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from stormlead_db import BuyerRow, LeadRow, StormRow, get_session

# fixed uuids — re-running this script must not create duplicates
STORM_ID = UUID("00000000-0000-0000-0000-000000000001")
BUYER_A_ID = UUID("00000000-0000-0000-0000-0000000000a1")
BUYER_B_ID = UUID("00000000-0000-0000-0000-0000000000a2")
LEAD_ID = UUID("00000000-0000-0000-0000-000000000010")

# placeholder sha256-shaped hash; smoke_e2e re-uses LEAD_ID with the
# real submitted-page hash, so the (phone, hash) uniqueness on leads
# doesn't collide between seed-lead and smoke-lead.
SEED_PAGE_HASH = "0" * 64


def _is_local_buyer_webhook_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip("[]").lower()
    if normalized in {"localhost", "host.docker.internal"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _buyer_webhook_base() -> str:
    value = os.environ.get(
        "STORMLEAD_LOCAL_BUYER_WEBHOOK_BASE",
        "http://host.docker.internal:9999",
    ).rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not _is_local_buyer_webhook_host(parsed.hostname):
        raise ValueError("STORMLEAD_LOCAL_BUYER_WEBHOOK_BASE must be local HTTP(S)")
    return value


BUYER_WEBHOOK_BASE = _buyer_webhook_base()


def _buyer_webhook_url(path: str) -> str:
    return f"{BUYER_WEBHOOK_BASE}/{path.lstrip('/')}"


async def _seed() -> dict[str, int]:
    now = datetime.now(UTC)
    async with get_session() as s:
        await s.execute(
            pg_insert(StormRow)
            .values(
                id=STORM_ID,
                external_id="seed-storm-001",
                name="seed test storm",
                source="nws",
                severity="warning",
                affected_states=["TX", "FL"],
                affected_counties=[],
                detected_at=now,
                raw={"_seed": True},
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        await s.execute(
            pg_insert(BuyerRow)
            .values(
                id=BUYER_A_ID,
                name="Buyer A",
                company="Storm Tree Co (TX)",
                contact_email="ops@storm-tree-tx.example",
                contact_phone_e164="+15125550199",
                status="active",
                webhook_url=_buyer_webhook_url("buyer-a"),
                webhook_secret="seedsecret-a",  # noqa: S106 - inert local seed secret
                bid_per_lead_t1_t2=Decimal("50.00"),
                bid_per_lead_t3=Decimal("200.00"),
                bid_per_call=Decimal("100.00"),
                filter_expression="lead.state == 'TX'",
                daily_cap=100,
                monthly_budget=Decimal("50000.00"),
                services=["tree_removal"],
                target_zips=["78701"],
                deposit_balance=Decimal("500.00"),
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "status": "active",
                    "webhook_url": _buyer_webhook_url("buyer-a"),
                    "webhook_secret": "seedsecret-a",
                    "filter_expression": "lead.state == 'TX'",
                    "daily_cap": 100,
                    "monthly_budget": Decimal("50000.00"),
                    "services": ["tree_removal"],
                    "target_zips": ["78701"],
                    "deposit_balance": Decimal("500.00"),
                },
            )
        )
        await s.execute(
            pg_insert(BuyerRow)
            .values(
                id=BUYER_B_ID,
                name="Buyer B",
                company="Florida Tree LLC",
                contact_email="ops@florida-tree.example",
                contact_phone_e164="+13055550199",
                status="active",
                webhook_url=_buyer_webhook_url("buyer-b"),
                webhook_secret="seedsecret-b",  # noqa: S106 - inert local seed secret
                bid_per_lead_t1_t2=Decimal("55.00"),
                bid_per_lead_t3=Decimal("220.00"),
                bid_per_call=Decimal("100.00"),
                filter_expression="lead.state == 'FL'",
                daily_cap=100,
                monthly_budget=Decimal("50000.00"),
                services=["tree_removal"],
                target_zips=["33101"],
                deposit_balance=Decimal("500.00"),
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "status": "active",
                    "webhook_url": _buyer_webhook_url("buyer-b"),
                    "webhook_secret": "seedsecret-b",
                    "filter_expression": "lead.state == 'FL'",
                    "daily_cap": 100,
                    "monthly_budget": Decimal("50000.00"),
                    "services": ["tree_removal"],
                    "target_zips": ["33101"],
                    "deposit_balance": Decimal("500.00"),
                },
            )
        )
        await s.execute(
            pg_insert(LeadRow)
            .values(
                id=LEAD_ID,
                source="landing_form",
                status="new",
                name="Test Homeowner",
                phone_e164="+15125550100",
                email="test@example.com",
                address_line1="123 Main St",
                city="Austin",
                state="TX",
                zip="78701",
                storm_id=STORM_ID,
                damage_description="oak limb on roof, no entry",
                damage_type="roof_impact",
                urgency="same_day",
                safety_flags=["roof_impact"],
                consent_text="I agree to be contacted by tree-removal contractors regarding storm damage.",
                consent_ip="203.0.113.1",
                consent_user_agent="Mozilla/5.0 (seed-dev)",
                consent_at=now,
                page_url="http://localhost:3000/austin-tx-tree-removal",
                page_html_hash=SEED_PAGE_HASH,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    return {"storms": 1, "buyers": 2, "leads": 1}


def main() -> None:
    counts = asyncio.run(_seed())
    print(
        f"seeded: {counts['storms']} storm, {counts['buyers']} buyers, "
        f"{counts['leads']} lead (idempotent)"
    )


if __name__ == "__main__":
    main()
