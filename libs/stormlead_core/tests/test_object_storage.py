from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from stormlead_core.object_storage import (
    InvalidObjectKeyError,
    LocalFilesystemObjectStorage,
    ObjectNotFoundError,
    local_object_storage_from_env,
)


def test_local_object_storage_writes_and_reads_metadata(tmp_path) -> None:
    storage = LocalFilesystemObjectStorage(tmp_path, allowed_prefixes=("local-demo/",))

    stored = storage.put_bytes("local-demo/run/photo.jpg", b"image", content_type="image/jpeg")

    assert stored.key == "local-demo/run/photo.jpg"
    assert stored.size_bytes == 5
    assert stored.sha256 == hashlib.sha256(b"image").hexdigest()
    assert stored.content_type == "image/jpeg"
    assert storage.exists(stored.key)
    assert storage.get_bytes(stored.key) == b"image"


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/local-demo/photo.jpg",
        "local-demo/../photo.jpg",
        "local-demo\\photo.jpg",
        "other/photo.jpg",
        "C:/local-demo/photo.jpg",
    ],
)
def test_local_object_storage_rejects_unsafe_keys(tmp_path, key: str) -> None:
    storage = LocalFilesystemObjectStorage(tmp_path, allowed_prefixes=("local-demo/",))

    with pytest.raises(InvalidObjectKeyError):
        storage.path_for_key(key)


def test_local_object_storage_requires_existing_key(tmp_path) -> None:
    storage = LocalFilesystemObjectStorage(tmp_path, allowed_prefixes=("local-demo/",))

    with pytest.raises(ObjectNotFoundError):
        storage.require_exists("local-demo/missing.jpg")


def test_local_object_storage_from_env_uses_first_configured_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORMLEAD_OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path))

    storage = local_object_storage_from_env("fallback", allowed_prefixes=("local-demo/",))

    assert storage.root == tmp_path


def test_local_object_storage_failed_replace_preserves_existing_object(
    monkeypatch, tmp_path
) -> None:
    storage = LocalFilesystemObjectStorage(tmp_path, allowed_prefixes=("local-demo/",))
    key = "local-demo/run/photo.jpg"
    storage.put_bytes(key, b"original")

    def fail_replace(self: Path, target: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError):
        storage.put_bytes(key, b"new")

    assert storage.get_bytes(key) == b"original"
