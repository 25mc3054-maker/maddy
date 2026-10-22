import json
import logging
from typing import Any

from app.database.db import get_connection

logger = logging.getLogger(__name__)

MAX_MESSAGES = 40


def _ensure_memory_table() -> None:
    """Create persistent conversation storage if needed."""

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_conversation_messages
            ON conversation_messages(conversation_id, id)
            """
        )


def get_history(
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Return recent messages in chronological order."""

    _ensure_memory_table()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM (
                SELECT id, role, content
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (conversation_id, MAX_MESSAGES),
        ).fetchall()

    history = []

    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning(
                "Skipping malformed saved conversation message."
            )
            continue

        history.append(
            {
                "role": row["role"],
                "content": content,
            }
        )

    return history


def add_message(
    conversation_id: str,
    message: dict[str, Any],
) -> None:
    """Persist a user or assistant message."""

    role = message.get("role")
    content = message.get("content")

    if role not in ("user", "assistant"):
        raise ValueError("Invalid conversation message role.")

    if not isinstance(content, list):
        raise ValueError("Message content must be a list.")

    _ensure_memory_table()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_messages
                (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                role,
                json.dumps(content, ensure_ascii=False),
            ),
        )

        conn.execute(
            """
            DELETE FROM conversation_messages
            WHERE conversation_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM conversation_messages
                  WHERE conversation_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (
                conversation_id,
                conversation_id,
                MAX_MESSAGES,
            ),
        )


def clear_history(conversation_id: str) -> None:
    """Delete the stored messages for one conversation."""

    _ensure_memory_table()

    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM conversation_messages
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        )
