from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from stormlead_db import LeadRow, get_session

REDACTABLE_STATUSES = ("nurtured", "dead", "sold")
RETENTION_DAYS = 730


def _redacted_phone(lead_id: object) -> str:
    digits = "".join(ch for ch in str(lead_id) if ch.isdigit())[-10:].rjust(10, "0")
    return f"+1{digits}"


async def redact_expired_leads(dry_run: bool = True) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    async with get_session() as session:
        leads = (
            (
                await session.execute(
                    select(LeadRow).where(
                        LeadRow.status.in_(REDACTABLE_STATUSES),
                        LeadRow.created_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        if dry_run:
            return len(leads)
        for lead in leads:
            lead.name = "[REDACTED]"
            lead.phone_e164 = _redacted_phone(lead.id)
            lead.email = None
            lead.address_line1 = "[REDACTED]"
        return len(leads)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Redact expired lead PII")
    parser.add_argument("--execute", action="store_true", help="apply redaction instead of dry-run")
    args = parser.parse_args()
    count = await redact_expired_leads(dry_run=not args.execute)
    mode = "execute" if args.execute else "dry_run"
    print(f"{mode}: {count} leads eligible for PII redaction")


if __name__ == "__main__":
    asyncio.run(_main())
