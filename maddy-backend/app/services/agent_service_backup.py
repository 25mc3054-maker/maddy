import json
from datetime import date
from typing import Any

from app.services.bedrock_service import converse
from app.services.task_service import (
    create_task,
    list_tasks,
    complete_task,
    get_daily_plan,
)


SYSTEM_PROMPT = """
You are MADDY, a capable personal AI assistant.

Your responsibilities include:
- Helping the user organize tasks and priorities.
- Understanding natural-language instructions.
- Using available tools when real application data or actions are needed.
- Giving concise, useful, honest responses.
- Maintaining conversational context using the supplied conversation history.

Rules:
- Never claim an action succeeded unless its tool succeeded.
- Never invent task IDs or task records.
- Ask for clarification if an important detail is ambiguous.
- Do not claim to access calendars, emails, files, or devices
  unless the relevant integration is actually available.
- Treat tool results as the source of truth.
- Do not perform unrelated actions.
- Use the current date supplied by the application when
  interpreting relative dates.
- Do not claim permanent memory unless information was
  actually saved to persistent storage.
"""


TOOLS = [
    {
        "toolSpec": {
            "name": "create_task",
            "description": (
                "Create a task in MADDY. Use this when the user "
                "asks to remember, schedule, or add a task."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short task title",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional task details",
                        },
                        "priority": {
                            "type": "string",
                            "enum": [
                                "low",
                                "medium",
                                "high",
                                "urgent",
                            ],
                        },
                        "due_date": {
                            "type": "string",
                            "description": (
                                "Optional due date in YYYY-MM-DD format"
                            ),
                        },
                    },
                    "required": [
                        "title",
                        "priority",
                    ],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_tasks",
            "description": (
                "List pending tasks, or all tasks when "
                "include_completed is true."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                        }
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "complete_task",
            "description": (
                "Mark an existing task as completed. "
                "Only use this when the user requests completion."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                        }
                    },
                    "required": ["task_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_daily_plan",
            "description": (
                "Get a prioritized plan based on MADDY's pending tasks."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
]


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute only explicitly approved MADDY tools."""

    if name == "create_task":
        task = create_task(
            title=arguments["title"],
            description=arguments.get("description", ""),
            priority=arguments.get("priority", "medium"),
            due_date=arguments.get("due_date"),
        )

        return {
            "success": True,
            "task": task,
        }

    if name == "list_tasks":
        tasks = list_tasks(
            include_completed=arguments.get(
                "include_completed",
                False,
            )
        )

        return {
            "success": True,
            "tasks": tasks,
        }

    if name == "complete_task":
        task = complete_task(
            task_id=int(arguments["task_id"])
        )

        return {
            "success": True,
            "task": task,
        }

    if name == "get_daily_plan":
        return {
            "success": True,
            "daily_plan": get_daily_plan(),
        }

    raise ValueError(f"Tool is not permitted: {name}")


def chat_with_maddy(
    conversation_history: list[dict[str, Any]] | str,
) -> dict:
    """
    Run a bounded Bedrock tool-calling loop.

    Accepts either a single user-message string or a list of
    Bedrock-compatible conversation messages.
    """

    if isinstance(conversation_history, str):
        user_message = conversation_history.strip()

        if not user_message:
            raise ValueError("Message cannot be empty.")

        messages = [
            {
                "role": "user",
                "content": [
                    {"text": user_message}
                ],
            }
        ]

    else:
        if not conversation_history:
            raise ValueError("Conversation history cannot be empty.")

        # Copy the history so this function doesn't mutate the
        # caller's original list.
        messages = [
            {
                "role": message["role"],
                "content": message["content"],
            }
            for message in conversation_history
        ]

        if messages[-1]["role"] != "user":
            raise ValueError(
                "The latest conversation message must be from the user."
            )

        if not any(
            block.get("text", "").strip()
            for block in messages[-1]["content"]
            if isinstance(block, dict)
        ):
            raise ValueError("Message cannot be empty.")

    tool_config = {
        "tools": TOOLS,
        "toolChoice": {"auto": {}},
    }

    tool_calls_executed = []

    for _ in range(5):
        response = converse(
            messages=messages,
            system=(
                SYSTEM_PROMPT
                + f"\nCurrent date: {date.today().isoformat()}"
            ),
            tool_config=tool_config,
        )

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        requested_tools = [
            block["toolUse"]
            for block in assistant_message.get("content", [])
            if "toolUse" in block
        ]

        if not requested_tools:
            answer = "\n".join(
                block["text"]
                for block in assistant_message.get("content", [])
                if "text" in block
            ).strip()

            return {
                "answer": answer,
                "reply": answer,
                "tool_calls": tool_calls_executed,
            }

        tool_results = []

        for tool in requested_tools:
            name = tool["name"]
            arguments = tool.get("input", {})

            try:
                result = execute_tool(name, arguments)

                tool_calls_executed.append({
                    "name": name,
                    "success": True,
                })

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool["toolUseId"],
                        "content": [
                            {
                                "text": json.dumps(
                                    result,
                                    default=str,
                                )
                            }
                        ],
                    }
                })

            except (ValueError, KeyError, TypeError) as error:
                tool_calls_executed.append({
                    "name": name,
                    "success": False,
                })

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool["toolUseId"],
                        "status": "error",
                        "content": [
                            {
                                "text": str(error)
                            }
                        ],
                    }
                })

        messages.append({
            "role": "user",
            "content": tool_results,
        })

    raise RuntimeError(
        "MADDY reached the maximum number of tool-calling rounds."
    )
