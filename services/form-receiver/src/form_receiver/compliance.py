from __future__ import annotations

import os
from typing import Any

import httpx
from stormlead_core import get_logger

log = get_logger(__name__)


async def verify_trustedform_cert(cert_url: str, api_key: str | None = None) -> dict[str, Any] | None:
    cert_url = cert_url.strip()
    key = api_key if api_key is not None else os.getenv("TRUSTEDFORM_API_KEY", "")
    if not cert_url or not key:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                cert_url,
                headers={"Authorization": f"Bearer {key}"},
                json={"retain": True},
            )
    except Exception as exc:
        log.warning("trustedform.verify_failed", error=str(exc))
        return None

    if response.status_code != 201:
        log.warning("trustedform.verify_soft_failed", status_code=response.status_code)
        return None

    return {"verified": True, "status_code": response.status_code}
