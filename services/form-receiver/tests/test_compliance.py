from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from form_receiver.compliance import verify_trustedform_cert


@pytest.mark.asyncio
async def test_verify_trustedform_empty_cert_returns_none() -> None:
    assert await verify_trustedform_cert("") is None


@pytest.mark.asyncio
async def test_verify_trustedform_empty_key_returns_none() -> None:
    assert await verify_trustedform_cert("https://cert.trustedform.test/abc", api_key="") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cert_url",
    [
        "http://cert.trustedform.com/abc",
        "https://evil.com/abc",
        "https://cert.trustedform.com.evil.com/abc",
        "https://10.0.0.1/abc",
        "https://[::1]/abc",
        "https://user:pass@cert.trustedform.com/abc",
    ],
)
async def test_verify_trustedform_rejects_untrusted_urls_without_request(cert_url: str) -> None:
    with patch("form_receiver.compliance.httpx.AsyncClient") as async_client:
        assert await verify_trustedform_cert(cert_url, api_key="test-key") is None
    async_client.assert_not_called()


@pytest.mark.asyncio
async def test_verify_trustedform_allowed_host_posts_retain_request() -> None:
    response = MagicMock(status_code=201)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with patch("form_receiver.compliance.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = client
        result = await verify_trustedform_cert(
            "https://cert.trustedform.com/abc", api_key="test-key"
        )

    assert result == {"verified": True, "status_code": 201}
    client.post.assert_awaited_once_with(
        "https://cert.trustedform.com/abc",
        headers={"Authorization": "Bearer test-key"},
        json={"retain": True},
    )
