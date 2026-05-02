"""create base tables via sqlalchemy.create_all, then alembic can apply
the timescale-hypertable + materialized-view migrations on top.

needed because libs/stormlead_db/migrations/versions/0001_initial.py
expects tables to already exist (it just runs `create_hypertable(...)`
calls). its docstring documents this pattern: "tables themselves are
created by `alembic revision --autogenerate` later. run AFTER the
autogen revision that creates the tables, OR run with `alembic stamp
head` to skip if already created by sqlalchemy.create_all in dev."

usage: DATABASE_URL=... uv run python scripts/init_db.py
       (called from `just migrate` before `alembic upgrade head`)
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine

from stormlead_db.tables import Base


def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    # use the sync psycopg driver for create_all; same dsn works with
    # the +psycopg suffix because we map to the sync driver implicitly
    # by stripping the async-specific bits.
    sync_dsn = dsn.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    engine = create_engine(sync_dsn)
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
    engine.dispose()
    print(f"create_all ok ({len(Base.metadata.tables)} tables)")


if __name__ == "__main__":
    main()
