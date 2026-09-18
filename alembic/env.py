import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the project root importable (alembic runs with its own working
# directory assumptions; this mirrors how app.py/tests import db.models).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import resolve_database_url  # noqa: E402
from db.models import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# The real DATABASE_URL comes from Streamlit secrets/environment via
# resolve_database_url() -- never from alembic.ini, so alembic.ini stays
# free of real credentials and safe to commit. This also means
# `alembic upgrade head` naturally targets whatever database your current
# environment is configured for (local SQLite by default, or the PostgreSQL
# URL in .streamlit/secrets.toml / DATABASE_URL if you've set one locally).
config.set_main_option("sqlalchemy.url", resolve_database_url())

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Our models' metadata -- this is what `alembic revision --autogenerate`
# diffs the live database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
