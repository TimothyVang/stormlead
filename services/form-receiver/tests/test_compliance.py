from __future__ import annotations

import pytest
from form_receiver.compliance import verify_trustedform_cert


@pytest.mark.asyncio
async def test_verify_trustedform_empty_cert_returns_none() -> None:
    assert await verify_trustedform_cert("") is None


@pytest.mark.asyncio
async def test_verify_trustedform_empty_key_returns_none() -> None:
    assert await verify_trustedform_cert("https://cert.trustedform.test/abc", api_key="") is None
