from __future__ import annotations

import csv
from io import StringIO

from sqlalchemy import select
from stormlead_db import LeadRow, get_session

HEADER = [
    "tracking_code",
    "name",
    "address_line1",
    "city",
    "state",
    "zip",
    "requested_service",
    "damage_description",
]


async def export_mailer_csv(
    state: str | None = None, service: str | None = None, status: str = "unsold"
) -> str:
    stmt = select(LeadRow).where(LeadRow.status == status)
    if state:
        stmt = stmt.where(LeadRow.state == state.upper())
    if service:
        stmt = stmt.where(LeadRow.requested_service == service.strip().lower())
    stmt = stmt.order_by(LeadRow.created_at.desc()).limit(5000)

    async with get_session() as session:
        rows = (await session.execute(stmt)).scalars().all()

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADER)
    for lead in rows:
        writer.writerow(
            [
                f"TRACK-{str(lead.id)[:8].upper()}",
                lead.name,
                lead.address_line1,
                lead.city,
                lead.state,
                lead.zip,
                lead.requested_service or "",
                (lead.damage_description or "")[:200],
            ]
        )
    return output.getvalue()
