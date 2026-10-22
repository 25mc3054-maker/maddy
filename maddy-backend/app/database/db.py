import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# Database directory and file
DATABASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = DATABASE_DIR / "maddy.db"


def get_connection() -> sqlite3.Connection:
    """
    Create and return a SQLite database connection.

    Row objects can be accessed using column names:
        row["id"]
        row["title"]
    """
    conn = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=30,
    )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    return conn


def initialize_database() -> None:
    """Create the database and task table if they do not exist."""

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'medium'
                    CHECK (
                        priority IN (
                            'low',
                            'medium',
                            'high',
                            'urgent'
                        )
                    ),
                due_date TEXT,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_completed
            ON tasks(completed)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_priority
            ON tasks(priority)
            """
        )


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    """
    Provide a database connection with automatic commit or rollback.

    Use this helper when a transaction needs explicit error handling.
    """
    conn = get_connection()

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
