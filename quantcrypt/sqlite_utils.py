from __future__ import annotations

import sqlite3
from pathlib import Path


SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
)


def prepare_sqlite_path(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect_sqlite(db_path: str | Path) -> sqlite3.Connection:
    path = prepare_sqlite_path(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    for pragma in SQLITE_PRAGMAS:
        connection.execute(pragma)
    return connection


def initialize_sqlite_schema(db_path: str | Path, schema_sql: str) -> None:
    with connect_sqlite(db_path) as connection:
        connection.executescript(schema_sql)
