from __future__ import annotations

import sqlite3
from pathlib import Path


DDL_PATH = Path(__file__).resolve().parents[2] / "db" / "ec101_standard_sqlite.sql"


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
