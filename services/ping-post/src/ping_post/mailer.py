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

_SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_csv_cell(value: object, *, limit: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value)
    if limit is not None:
        text = text[:limit]
    if text.lstrip().startswith(_SPREADSHEET_FORMULA_PREFIXES):
        return f"'{text}"
    return text


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
                _safe_csv_cell(lead.name),
                _safe_csv_cell(lead.address_line1),
                _safe_csv_cell(lead.city),
                _safe_csv_cell(lead.state),
                _safe_csv_cell(lead.zip),
                _safe_csv_cell(lead.requested_service),
                _safe_csv_cell(lead.damage_description, limit=200),
            ]
        )
    return output.getvalue()
