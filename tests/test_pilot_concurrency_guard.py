"""The pilot-search page's guard against overlapping runs.

A pilot run holds its database connection for the whole search (one YouTube
API call per query). Streamlit cannot interrupt a script blocked on the
network, so a second click starts a concurrent run holding a second
connection; enough repeats exhaust the pool and every page then fails on
connection checkout with sqlalchemy.exc.TimeoutError -- which is how this
surfaced in production, as a failure inside init_db() on an unrelated page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from db import crud

# AppTest resolves a relative path against the file that calls from_file(),
# which would be tests/ -- so give it an absolute path from the repo root.
PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "04_pilot_search.py")
FLAG = "pilot_search_in_progress"


@pytest.fixture()
def pilot_page(monkeypatch, tmp_path):
    """The pilot page, backed by a temp SQLite database seeded far enough to
    reach the 'Run pilot search' button (a study, a reviewer, an active
    query, and an apparently-configured API key)."""
    import db.database as database

    saved = (database._engine, database._backend, database._SessionLocal, database._schema_ready)
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_backend", None)
    monkeypatch.setattr(database, "_SessionLocal", None)
    monkeypatch.setattr(database, "_schema_ready", False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "pilot.db"))
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-used")

    database.init_db()
    session = database.get_session()
    study = crud.create_study(session, name="Guard study")
    crud.create_reviewer(session, name="Rev", initials="RV")
    crud.create_search_query(session, study_id=study.id, query_text="buses")
    session.commit()
    session.close()

    from streamlit.testing.v1 import AppTest

    yield AppTest.from_file(PAGE, default_timeout=60)

    (database._engine, database._backend, database._SessionLocal, database._schema_ready) = saved


def test_page_renders_and_offers_the_run_button(pilot_page):
    pilot_page.run()
    assert not pilot_page.exception, [str(e) for e in pilot_page.exception]
    assert any(b.label == "Run pilot search" for b in pilot_page.button)


def test_second_run_is_refused_while_one_is_in_progress(pilot_page):
    """With the flag already set -- i.e. another script run is mid-search --
    clicking must refuse rather than start a second concurrent run."""
    pilot_page.session_state[FLAG] = True
    pilot_page.run()

    button = next(b for b in pilot_page.button if b.label == "Run pilot search")
    button.click().run()

    assert not pilot_page.exception, [str(e) for e in pilot_page.exception]
    warnings = [w.value for w in pilot_page.warning]
    assert any("already running" in w for w in warnings), warnings


def test_guard_clears_even_when_the_search_raises(pilot_page, monkeypatch):
    """A stuck flag would block every later search in the session, so the
    clear has to happen on the failure path too."""
    from services import pilot_service

    def _boom(*args, **kwargs):
        raise RuntimeError("YouTube API exploded")

    monkeypatch.setattr(pilot_service, "run_pilot_search", _boom)

    pilot_page.run()
    button = next(b for b in pilot_page.button if b.label == "Run pilot search")
    button.click().run()

    # The page surfaces the error, but the guard must not stay latched.
    assert pilot_page.session_state[FLAG] is False
