"""Database URL / secret resolution (Streamlit Cloud + PostgreSQL migration,
sections 4-5): Streamlit secrets -> environment variable -> local SQLite
fallback, with production refusing the SQLite fallback outright."""

from __future__ import annotations

import pytest

from db.database import ConfigurationError, get_secret, is_production, resolve_database_url


@pytest.fixture(autouse=True)
def _no_streamlit_secrets(monkeypatch):
    """get_secret() tries st.secrets first; force it to behave as if no
    secrets.toml exists (raises), isolating these tests to the env-var path
    regardless of whether this machine happens to have a local secrets file."""
    import streamlit as st

    class _NoSecrets:
        def __contains__(self, _key):
            raise FileNotFoundError("no secrets.toml in this test")

    monkeypatch.setattr(st, "secrets", _NoSecrets())


def test_get_secret_reads_env_var_when_no_streamlit_secret(monkeypatch):
    monkeypatch.setenv("SOME_TEST_KEY", "from-env")
    assert get_secret("SOME_TEST_KEY") == "from-env"


def test_get_secret_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_TEST_KEY", raising=False)
    assert get_secret("SOME_TEST_KEY", "fallback") == "fallback"
    assert get_secret("SOME_TEST_KEY") is None


def test_is_production_defaults_to_false(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert is_production() is False


def test_is_production_true_only_when_explicitly_set(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert is_production() is True
    monkeypatch.setenv("APP_ENV", "Production")  # case-insensitive
    assert is_production() is True
    monkeypatch.setenv("APP_ENV", "development")
    assert is_production() is False
    monkeypatch.setenv("APP_ENV", "staging")
    assert is_production() is False  # only the literal value "production" counts


def test_resolve_database_url_prefers_database_url_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")
    assert resolve_database_url() == "postgresql+psycopg://user:pass@host:5432/db"


def test_resolve_database_url_falls_back_to_sqlite_in_development(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "dev.db"))

    url = resolve_database_url()
    assert url.startswith("sqlite:///")
    assert str(tmp_path / "dev.db") in url


def test_resolve_database_url_raises_in_production_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ConfigurationError) as exc_info:
        resolve_database_url()
    assert "DATABASE_URL" in str(exc_info.value)


def test_resolve_database_url_works_in_production_with_database_url_set(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")

    assert resolve_database_url() == "postgresql+psycopg://user:pass@host:5432/db"


def test_configuration_error_message_is_static_and_leaks_nothing(monkeypatch):
    """The production config error is shown directly in the Streamlit UI (see
    app.py's ConfigurationError handler) -- it must be a fixed message, never
    one that interpolates a secret value (e.g. a partially-set DATABASE_URL)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIzaSuperSecretKeyValue")

    with pytest.raises(ConfigurationError) as exc_info:
        resolve_database_url()
    assert "AIzaSuperSecretKeyValue" not in str(exc_info.value)
