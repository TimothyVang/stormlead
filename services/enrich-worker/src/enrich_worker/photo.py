from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx
from stormlead_core import get_logger

log = get_logger(__name__)


def _extract_json(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        text = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    else:
        text = str(content or "")
    if not text.strip():
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


async def classify_photo(image_bytes: bytes) -> dict[str, Any] | None:
    if not image_bytes:
        return None

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    base_url = os.getenv("LITELLM_PROXY_URL", "http://litellm:4000").rstrip("/")
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("LITELLM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": "claude-vision",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Classify storm damage. Return only JSON with keys: "
                            "damage_tier, damage_type, confidence, notes."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/v1/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        log.warning("photo.classification_failed", error=str(exc))
        return None

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    result = _extract_json(content)
    if result is None:
        return None
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    if confidence < 0.7:
        return None
    result["confidence"] = confidence
    return result
