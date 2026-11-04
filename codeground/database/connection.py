"""
Database connection factory and initialization.
Enforces WAL mode, foreign key constraints, and isolated transactions.
"""
import sqlite3
from typing import Generator
from contextlib import contextmanager
from pathlib import Path
from config.settings import DATABASE_URL, SCHEMA_PATH


def get_db_connection(db_path: str = DATABASE_URL) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Configure WAL journal mode and foreign key constraints
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def transaction(db_path: str = DATABASE_URL) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for atomic database operations with automatic rollback on failure."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database(db_path: str = DATABASE_URL, schema_file: Path = SCHEMA_PATH) -> None:
    """Creates all required tables and indexes using the master schema file."""
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file missing at: {schema_file}")
    
    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with transaction(db_path) as conn:
        conn.executescript(schema_sql)
