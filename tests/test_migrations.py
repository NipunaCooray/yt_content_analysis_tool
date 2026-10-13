"""Alembic revisions, checked without touching any database.

Never run `alembic upgrade` from a test against a real database: env.py
resolves DATABASE_URL from .streamlit/secrets.toml first, which may point at
production. Offline mode (sql=True) only renders the SQL, and conftest's
autouse fixture already hides st.secrets, so the dummy URL below is used.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def test_single_head_is_the_one_record_per_video_revision():
    assert ScriptDirectory.from_config(_config()).get_heads() == ["8b1d6e4f2c70"]


def test_accuracy_notes_migration_is_additive_and_nullable(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://offline:offline@localhost/never_connected")
    command.upgrade(_config(), "658c4b61b5e1:3f9c2a7d4e1b", sql=True)
    sql = capsys.readouterr().out
    assert "ALTER TABLE video_coding ADD COLUMN accuracy_notes TEXT;" in sql
    assert "DROP" not in sql.upper()
    assert "NOT NULL" not in sql.upper()


def test_one_record_per_video_migration_only_adds_unique_constraints(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://offline:offline@localhost/never_connected")
    command.upgrade(_config(), "3f9c2a7d4e1b:8b1d6e4f2c70", sql=True)
    sql = capsys.readouterr().out
    assert ("ALTER TABLE screening_decisions ADD CONSTRAINT uq_screening_study_video "
            "UNIQUE (study_id, video_id);") in sql
    assert ("ALTER TABLE video_coding ADD CONSTRAINT uq_video_coding_study_video "
            "UNIQUE (study_id, video_id);") in sql
    assert "DROP" not in sql.upper()
    assert "DELETE" not in sql.upper()
