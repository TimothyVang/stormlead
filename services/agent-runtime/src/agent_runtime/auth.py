"""LiteLLM proxy configuration for agent model calls."""

from __future__ import annotations

import os


def litellm_base_url() -> str:
    return os.getenv("LITELLM_PROXY_URL", "http://litellm:4000").rstrip("/")


def litellm_chat_completions_url() -> str:
    return f"{litellm_base_url()}/v1/chat/completions"


def litellm_headers() -> dict[str, str]:
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
