from __future__ import annotations

import ast
from pathlib import Path

import pytest
from agent_runtime.auth import litellm_chat_completions_url, litellm_headers
from agent_runtime.execution import _completion_payload, _extract_completion_text

AGENT_RUNTIME_SRC = Path(__file__).resolve().parents[1] / "src" / "agent_runtime"
FORBIDDEN_IMPORTS = {"anthropic", "claude_agent_sdk", "openai"}


def test_litellm_endpoint_uses_proxy_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://litellm.local:4000/")
    assert litellm_chat_completions_url() == "http://litellm.local:4000/v1/chat/completions"


def test_litellm_headers_use_virtual_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")
    assert litellm_headers()["Authorization"] == "Bearer sk-test"


def test_litellm_headers_do_not_use_upstream_provider_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-provider-key")

    assert "Authorization" not in litellm_headers()


def test_completion_payload_is_openai_compatible() -> None:
    payload = _completion_payload(
        model="agent-default",
        system_prompt="system",
        prompt="user",
        max_tokens=100,
    )
    assert payload == {
        "model": "agent-default",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "max_tokens": 100,
    }


def test_extract_completion_text_from_litellm_response() -> None:
    assert _extract_completion_text({"choices": [{"message": {"content": "result"}}]}) == "result"


def test_agent_runtime_does_not_import_direct_provider_sdks() -> None:
    violations: list[str] = []
    for path in AGENT_RUNTIME_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module.split(".", 1)[0]}
            else:
                continue
            blocked = names & FORBIDDEN_IMPORTS
            if blocked:
                violations.append(f"{path.relative_to(AGENT_RUNTIME_SRC)} imports {blocked}")
    assert violations == []
