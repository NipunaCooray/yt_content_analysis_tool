#!/usr/bin/env python3
"""
One-time migration of an existing local SQLite research database into
PostgreSQL, for teams that started collecting data before moving to the
Streamlit Cloud + PostgreSQL production setup.

If your existing SQLite data is only disposable development data, you don't
need this script -- just run `alembic upgrade head` against the new
PostgreSQL database and start collecting real data there directly.

Usage:

    # Uses the local dev SQLite file and DATABASE_URL (secrets/env) by default:
    python scripts/migrate_sqlite_to_postgres.py --dry-run
    python scripts/migrate_sqlite_to_postgres.py

    # Or specify both explicitly:
    python scripts/migrate_sqlite_to_postgres.py \\
        --sqlite-url sqlite:///data/research_tool.db \\
        --postgres-url postgresql+psycopg://USER:PASSWORD@HOST:PORT/postgres

What it does:
    1. Connects to the SQLite source and the PostgreSQL target.
    2. Creates the target schema if it doesn't exist yet (a convenience
       fallback -- prefer `alembic upgrade head` for a schema that's meant
       to evolve with the models over time).
    3. Migrates every table in FK-dependency order (derived automatically
       from the SQLAlchemy models, so it never drifts from the actual schema).
    4. Preserves primary keys, timestamps, and foreign-key relationships
       (by copying every column as-is, including the id).
    5. Skips rows whose primary key already exists in the target -- safe to
       re-run after fixing an issue partway through, and won't duplicate a
       table you already migrated.
    6. Resets each table's PostgreSQL identity/serial sequence to past the
       highest migrated id, so new rows created via the app afterwards don't
       collide with migrated ones.
    7. Reports a before/after row count per table.

Always run with --dry-run first, and keep the SQLite file as an archival
backup until you've verified the migration (see handover doc's PostgreSQL
migration, section 22).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, insert, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from db.database import get_database_path, resolve_database_url  # noqa: E402
from db.models import Base  # noqa: E402


def _redact(url: str) -> str:
    """host/db only, never the credentials -- safe to print to the terminal."""
    if "@" in url:
        return "..." + url.split("@", 1)[1]
    return url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--sqlite-url", default=None,
        help="Source SQLite URL (default: the local dev SQLite file db/database.py uses)",
    )
    parser.add_argument(
        "--postgres-url", default=None,
        help="Target PostgreSQL URL (default: DATABASE_URL from Streamlit secrets/environment)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report row counts only; write nothing to the target",
    )
    return parser.parse_args()


def migrate(sqlite_url: str, postgres_url: str, dry_run: bool) -> list[tuple[str, int, int, str]]:
    source_engine: Engine = create_engine(sqlite_url)
    target_engine: Engine = create_engine(postgres_url)

    if not dry_run:
        # Convenience fallback for a brand-new database; prefer `alembic
        # upgrade head` as the source of truth for schema going forward.
        Base.metadata.create_all(target_engine)

    tables = Base.metadata.sorted_tables  # topologically sorted by FK dependency
    report: list[tuple[str, int, int, str]] = []

    with source_engine.connect() as src_conn, target_engine.connect() as tgt_conn:
        for table in tables:
            src_rows = list(src_conn.execute(select(table)).mappings())
            src_count = len(src_rows)

            if dry_run:
                report.append((table.name, src_count, 0, "dry run -- not written"))
                continue

            pk_cols = [c.name for c in table.primary_key.columns]
            existing_ids: set[tuple] = set()
            if pk_cols and src_rows:
                existing_ids = {
                    tuple(row) for row in tgt_conn.execute(select(*[table.c[c] for c in pk_cols]))
                }

            inserted = 0
            skipped = 0
            for row in src_rows:
                key = tuple(row[c] for c in pk_cols) if pk_cols else None
                if key is not None and key in existing_ids:
                    skipped += 1
                    continue
                tgt_conn.execute(insert(table).values(**dict(row)))
                inserted += 1
            tgt_conn.commit()

            # Preserving explicit ids bypasses PostgreSQL's identity/serial
            # sequence, so the next auto-generated id (created normally via
            # the app afterwards) could otherwise collide with a migrated
            # row. Bump the sequence past the highest id we just wrote.
            # (PostgreSQL-only -- other targets, e.g. SQLite in tests, don't
            # have sequences to fix up.)
            if "id" in table.c and target_engine.dialect.name == "postgresql":
                tgt_conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table.name}), 1))"
                ))
                tgt_conn.commit()

            tgt_count = len(list(tgt_conn.execute(select(table)).mappings()))
            note = f"+{inserted} inserted" + (f", {skipped} already present (skipped)" if skipped else "")
            report.append((table.name, src_count, tgt_count, note))

    return report


def main() -> None:
    args = parse_args()

    sqlite_url = args.sqlite_url or f"sqlite:///{get_database_path()}"
    postgres_url = args.postgres_url or resolve_database_url()

    if postgres_url.startswith("sqlite"):
        print(
            "ERROR: the target URL resolved to SQLite, not PostgreSQL "
            f"({_redact(postgres_url)}). Pass --postgres-url explicitly, or set DATABASE_URL "
            "(and APP_ENV=production, or use --postgres-url) so it doesn't fall back to the "
            "local SQLite default."
        )
        sys.exit(1)

    print(f"Source (SQLite):     {sqlite_url}")
    print(f"Target (PostgreSQL): {_redact(postgres_url)}")
    if args.dry_run:
        print("\nDRY RUN -- no data will be written.\n")
    else:
        print()

    report = migrate(sqlite_url, postgres_url, args.dry_run)

    header = f"{'Table':<28} {'SQLite':>8} {'Postgres':>10}  Notes"
    print(header)
    print("-" * len(header))
    for name, src_count, tgt_count, note in report:
        tgt_display = "-" if args.dry_run else tgt_count
        print(f"{name:<28} {src_count:>8} {str(tgt_display):>10}  {note}")

    if args.dry_run:
        print("\nThis was a dry run. Re-run without --dry-run to actually migrate.")
    else:
        print(
            "\nMigration complete. Compare the row counts above (see handover doc's PostgreSQL "
            "migration, section 22), then manually spot-check a few representative "
            "relationships (a study -> its videos -> screening decisions -> coding records). "
            "Keep the SQLite file as an archival backup until you're confident in the result."
        )


if __name__ == "__main__":
    main()
