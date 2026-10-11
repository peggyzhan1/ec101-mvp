from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


DDL_PATH = Path(__file__).resolve().parents[2] / "db" / "ec101_standard_sqlite.sql"
MIGRATIONS_PATH = DDL_PATH.parent / "migrations"


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(path)
    try:
        connection.executescript(DDL_PATH.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def upgrade_database(path: Path) -> None:
    connection = connect_database(path)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.commit()
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration")
        }
        for migration_path in sorted(MIGRATIONS_PATH.glob("*.sql")):
            version = migration_path.stem
            if version in applied:
                continue
            applied_at = datetime.now().isoformat(timespec="seconds").replace("'", "''")
            version_sql = version.replace("'", "''")
            script = migration_path.read_text(encoding="utf-8")
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{script}\n"
                "INSERT INTO schema_migration(version, applied_at) "
                f"VALUES ('{version_sql}', '{applied_at}');\n"
                "COMMIT;"
            )
        _backfill_platform_customer_identities(connection)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def _backfill_platform_customer_identities(connection: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not {"customer", "import_batch", "platform_customer_identity"} <= tables:
        return
    rows = connection.execute(
        "SELECT c.dealer_platform_id, c.customer_no, c.customer_name, "
        "COALESCE(c.added_at, ib.imported_at) AS seen_at "
        "FROM customer c JOIN import_batch ib ON ib.import_batch_id = c.import_batch_id "
        "WHERE c.customer_no <> '' ORDER BY seen_at, c.customer_id"
    ).fetchall()
    with connection:
        for row in rows:
            connection.execute(
                "INSERT INTO platform_customer_identity "
                "(dealer_platform_id, platform_customer_no, latest_customer_name, "
                "first_seen_at, last_seen_at, status) VALUES (?, ?, ?, ?, ?, 'active') "
                "ON CONFLICT(dealer_platform_id, platform_customer_no) DO UPDATE SET "
                "latest_customer_name = excluded.latest_customer_name, "
                "last_seen_at = excluded.last_seen_at, status = 'active'",
                (row[0], row[1], row[2], row[3], row[3]),
            )
