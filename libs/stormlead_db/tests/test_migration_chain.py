from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
CURRENT_HEAD = "0023_learning_proposals"


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revision_value(value: object) -> str | None:
    if value is None:
        return None
    assert isinstance(value, str)
    return value


def test_alembic_migrations_form_one_linear_chain_to_current_head() -> None:
    modules = [_load_migration(path) for path in sorted(MIGRATION_DIR.glob("*.py"))]
    revisions: dict[str, ModuleType] = {}
    down_revisions: dict[str, str | None] = {}

    for module in modules:
        revision = _revision_value(getattr(module, "revision", None))
        assert revision is not None
        assert revision not in revisions
        assert getattr(module, "branch_labels", None) is None
        assert getattr(module, "depends_on", None) is None
        assert callable(getattr(module, "upgrade", None))
        assert callable(getattr(module, "downgrade", None))
        revisions[revision] = module
        down_revisions[revision] = _revision_value(getattr(module, "down_revision", None))

    referenced_revisions = {
        revision for revision in down_revisions.values() if revision is not None
    }
    assert referenced_revisions <= set(revisions)
    assert {revision for revision, down in down_revisions.items() if down is None} == {
        "0001_initial"
    }
    assert set(revisions) - referenced_revisions == {CURRENT_HEAD}

    walked_revisions: list[str] = []
    current_revision: str | None = CURRENT_HEAD
    while current_revision is not None:
        assert current_revision not in walked_revisions
        walked_revisions.append(current_revision)
        current_revision = down_revisions[current_revision]

    assert set(walked_revisions) == set(revisions)
    assert walked_revisions[-1] == "0001_initial"
