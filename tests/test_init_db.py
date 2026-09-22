"""init_db() schema preparation.

init_db() runs at app.py module level, so it executes on *every* Streamlit
script run -- every page load and every button click. It used to call
create_all() each time, which against PostgreSQL issued one reflection query
per table (18 round trips) just to rediscover that every table already
existed, holding a pooled connection throughout. These tests pin down that it
now does its work once and then gets out of the way, and that PostgreSQL is
left to Alembic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import inspect

import db.database as database
from db.database import ConfigurationError


@pytest.fixture()
def fresh_database_module(monkeypatch, tmp_path):
    """Reset db.database's lazy globals so a test gets a clean engine, and
    restore them afterwards -- they are process-wide, so leaking them would
    corrupt unrelated tests."""
    saved = (
        database._engine,
        database._backend,
        database._SessionLocal,
        database._schema_ready,
    )
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_backend", None)
    monkeypatch.setattr(database, "_SessionLocal", None)
    monkeypatch.setattr(database, "_schema_ready", False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "init.db"))
    yield
    (
        database._engine,
        database._backend,
        database._SessionLocal,
        database._schema_ready,
    ) = saved


def test_init_db_creates_sqlite_schema(fresh_database_module):
    database.init_db()
    tables = set(inspect(database.get_engine()).get_table_names())
    assert "studies" in tables and "videos" in tables


def test_init_db_is_a_noop_after_the_first_call(fresh_database_module, monkeypatch):
    """The regression that matters: a second call must not touch the database.

    Against PostgreSQL the repeated call cost 18 round trips and a pooled
    connection on every single script run.
    """
    database.init_db()

    create_all = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", create_all)
    migrations = MagicMock()
    monkeypatch.setattr(database, "_apply_sqlite_column_migrations", migrations)

    for _ in range(5):
        database.init_db()

    create_all.assert_not_called()
    migrations.assert_not_called()


def test_init_db_does_not_run_create_all_against_postgres(fresh_database_module, monkeypatch):
    """Alembic owns the PostgreSQL schema. create_all() must never run there:
    besides the per-table reflection cost, it does not stamp alembic_version,
    so a schema it created would break the next `alembic upgrade head`."""
    monkeypatch.setattr(database, "get_backend_name", lambda: "postgresql")
    monkeypatch.setattr(database, "_verify_postgres_schema", lambda _engine: None)

    create_all = MagicMock()
    monkeypatch.setattr(database.Base.metadata, "create_all", create_all)

    database.init_db()

    create_all.assert_not_called()


def _engine_reporting(migrated: bool) -> MagicMock:
    """A stand-in engine whose single scalar() answers the alembic_version
    existence probe, so the guard's branches can be tested without Postgres."""
    conn = MagicMock()
    conn.exec_driver_sql.return_value.scalar.return_value = migrated
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_verify_postgres_schema_passes_on_a_migrated_database():
    database._verify_postgres_schema(_engine_reporting(True))  # must not raise


def test_verify_postgres_schema_refuses_an_unmigrated_database():
    with pytest.raises(ConfigurationError) as exc_info:
        database._verify_postgres_schema(_engine_reporting(False))
    # The message is shown in the UI by app.py -- it should say what to do.
    assert "alembic upgrade head" in str(exc_info.value)


def test_verify_postgres_schema_uses_a_single_round_trip():
    """The check runs at process start against a remote database; it should
    cost one query, not a reflection sweep."""
    engine = _engine_reporting(True)
    database._verify_postgres_schema(engine)
    conn = engine.connect.return_value.__enter__.return_value
    assert conn.exec_driver_sql.call_count == 1
