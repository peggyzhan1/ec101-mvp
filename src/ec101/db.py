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
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
