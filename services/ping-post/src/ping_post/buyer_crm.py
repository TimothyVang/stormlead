from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import array
from stormlead_db import BuyerRow, get_session


async def check_exclusive_zip_conflict(
    buyer_id: UUID | None, exclusive_zips: list[str]
) -> None:
    zips = sorted({zip_.strip() for zip_ in exclusive_zips if zip_.strip()})
    if not zips:
        return

    async with get_session() as session:
        stmt = select(BuyerRow.id, BuyerRow.company, BuyerRow.exclusive_zips).where(
            BuyerRow.status == "active",
            BuyerRow.exclusive_zips.op("?|")(array(zips)),
        )
        if buyer_id is not None:
            stmt = stmt.where(BuyerRow.id != buyer_id)
        rows = (await session.execute(stmt)).all()

    conflicts = []
    requested = set(zips)
    for row_id, company, existing in rows:
        overlap = requested.intersection(existing or [])
        if overlap:
            conflicts.append({"buyer_id": str(row_id), "company": company, "zips": sorted(overlap)})
    if conflicts:
        ids = [conflict["buyer_id"] for conflict in conflicts]
        raise HTTPException(status_code=409, detail=f"ZIP conflict with buyers: {ids}")
