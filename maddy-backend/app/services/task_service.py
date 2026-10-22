from typing import Any

from app.database.db import get_connection


VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: str | None = None,
) -> dict[str, Any]:
    """Create a task and return the saved task."""

    title = title.strip()
    description = description.strip()
    priority = priority.lower().strip()

    if not title:
        raise ValueError("Task title cannot be empty.")

    if priority not in VALID_PRIORITIES:
        raise ValueError(
            "Priority must be low, medium, high, or urgent."
        )

    if due_date:
        due_date = due_date.strip() or None

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tasks (title, description, priority, due_date)
            VALUES (?, ?, ?, ?)
            """,
            (title, description, priority, due_date),
        )

        task_id = cursor.lastrowid

        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

        connection.commit()

        return dict(row)


def list_tasks(
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    """Return tasks ordered by priority and creation time."""

    query = """
        SELECT * FROM tasks
    """

    if not include_completed:
        query += " WHERE completed = 0"

    query += """
        ORDER BY
            CASE priority
                WHEN 'urgent' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
            END,
            id DESC
    """

    with get_connection() as connection:
        rows = connection.execute(query).fetchall()

        return [dict(row) for row in rows]


def complete_task(task_id: int) -> dict[str, Any]:
    """Mark a task as completed."""

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE tasks
            SET completed = 1
            WHERE id = ?
            """,
            (task_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(f"Task {task_id} was not found.")

        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

        connection.commit()

        return dict(row)


def get_daily_plan() -> dict[str, Any]:
    """Build a basic daily plan from unfinished tasks."""

    tasks = list_tasks()

    priority_order = {
        "urgent": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    tasks.sort(
        key=lambda task: (
            priority_order[task["priority"]],
            task["due_date"] or "9999-12-31",
            task["id"],
        )
    )

    return {
        "total_pending": len(tasks),
        "urgent_tasks": [
            task for task in tasks
            if task["priority"] == "urgent"
        ],
        "recommended_order": tasks,
    }