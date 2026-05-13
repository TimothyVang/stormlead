from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class ObjectStorageError(RuntimeError):
    """Base error for StormLead object-storage operations."""


class InvalidObjectKeyError(ObjectStorageError):
    """Raised when an object key can escape the configured storage root."""


class ObjectNotFoundError(ObjectStorageError):
    """Raised when an object key is valid but not present."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str
    content_type: str | None = None


class LocalFilesystemObjectStorage:
    def __init__(self, root: str | Path, *, allowed_prefixes: tuple[str, ...] = ()) -> None:
        self.root = Path(root)
        self.allowed_prefixes = tuple(prefix for prefix in allowed_prefixes if prefix)

    def validate_key(self, key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise InvalidObjectKeyError("object key is required")
        normalized = key.strip()
        if normalized.startswith("/") or ":" in normalized or "\\" in normalized:
            raise InvalidObjectKeyError("object key must be relative")
        key_path = Path(normalized)
        if key_path.is_absolute() or ".." in key_path.parts:
            raise InvalidObjectKeyError("object key must stay under storage root")
        if self.allowed_prefixes and not any(
            normalized.startswith(prefix) for prefix in self.allowed_prefixes
        ):
            raise InvalidObjectKeyError("object key prefix is not allowed")
        return normalized

    def path_for_key(self, key: str) -> Path:
        normalized = self.validate_key(key)
        root = self.root.resolve()
        path = (root / normalized).resolve()
        if not path.is_relative_to(root):
            raise InvalidObjectKeyError("object key resolved outside storage root")
        return path

    def exists(self, key: str) -> bool:
        return self.path_for_key(key).is_file()

    def require_exists(self, key: str) -> str:
        normalized = self.validate_key(key)
        if not self.exists(normalized):
            raise ObjectNotFoundError("object key does not exist")
        return normalized

    def get_bytes(self, key: str) -> bytes | None:
        path = self.path_for_key(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def put_bytes(
        self, key: str, content: bytes, *, content_type: str | None = None
    ) -> StoredObject:
        normalized = self.validate_key(key)
        path = self.path_for_key(normalized)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(content)
            temp_path.replace(path)
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise
        return StoredObject(
            key=normalized,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_type=content_type,
        )


def local_object_storage_from_env(
    default_root: str | Path,
    *,
    env_names: tuple[str, ...] = ("STORMLEAD_OBJECT_STORAGE_LOCAL_ROOT",),
    allowed_prefixes: tuple[str, ...] = (),
) -> LocalFilesystemObjectStorage:
    configured = next(
        (os.getenv(name, "").strip() for name in env_names if os.getenv(name, "").strip()),
        "",
    )
    root = Path(configured) if configured else Path(default_root)
    return LocalFilesystemObjectStorage(root, allowed_prefixes=allowed_prefixes)
