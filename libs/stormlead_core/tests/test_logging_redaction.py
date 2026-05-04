import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("stormlead_core_logging", Path("libs/stormlead_core/src/stormlead_core/logging.py"))
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
redact_pii = _mod.redact_pii


def test_redact_pii_masks_phone_email_address() -> None:
    event = {
        "msg": "contact me at jane.doe@example.com or +1 (512) 555-9988",
        "address": "123 Main St",
        "nested": {"email": "a@b.com"},
    }
    out = redact_pii(None, None, event)
    assert "example.com" in out["msg"]
    assert "j***@example.com" in out["msg"]
    assert "***-***-9988" in out["msg"]
    assert out["address"] == "[REDACTED_ADDRESS]"
    assert out["nested"]["email"] == "a***@b.com"
