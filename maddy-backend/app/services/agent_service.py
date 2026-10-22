import anyio
import json
import logging

from datetime import date
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.services.bedrock_service import converse


logger = logging.getLogger(__name__)

MCP_SERVER_URL = "http://127.0.0.1:8001/mcp"
MAX_TOOL_ROUNDS = 5


class MCPConnectionError(RuntimeError):
    """The MCP endpoint could not be reached or completed a protocol call."""


class MCPToolError(RuntimeError):
    """MCP returned a protocol or business-level tool failure."""


class BedrockRequestError(RuntimeError):
    """Bedrock failed to return a usable Converse response."""


SYSTEM_PROMPT = """
You are MADDY, a capable personal AI assistant.

Your responsibilities include:
- Helping users organize tasks and priorities.
- Understanding natural-language instructions.
- Using available MCP tools when application data or actions are needed.
- Giving concise, useful, honest responses.
- Maintaining conversational context using supplied conversation history.

Rules:
- Never claim an action succeeded unless its tool succeeded.
- Never invent task IDs or task records.
- Ask for clarification if an important detail is ambiguous.
- Smart-home tools change simulation-only state stored in SQLite; never imply
  that physical devices were controlled.
- Resolve device names against the registered inventory. For plural requests,
  act only on matching registered devices and name each affected device.
- If the requested device is not registered, report that instead of choosing
  a different device.
- Do not claim access to calendars, emails, files, or devices
  unless the relevant integration is actually available.
- Treat tool results as the source of truth.
- Do not perform unrelated actions.
- Interpret relative dates using the current date supplied below.
- Do not claim permanent memory unless information was
  actually saved to persistent storage.
"""


async def discover_mcp_tools() -> list[dict]:
    """Discover tools exposed by the running MADDY MCP server."""

    try:
        async with streamable_http_client(MCP_SERVER_URL) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()

                bedrock_tools = []
                for tool in result.tools:
                    schema = tool.input_schema or {
                        "type": "object",
                        "properties": {},
                    }
                    bedrock_tools.append({
                        "toolSpec": {
                            "name": tool.name,
                            "description": tool.description
                            or f"Execute the {tool.name} tool.",
                            "inputSchema": {"json": schema},
                        }
                    })

                logger.info(
                    "Discovered %s MCP tools: %s",
                    len(bedrock_tools),
                    [item["toolSpec"]["name"] for item in bedrock_tools],
                )
                return bedrock_tools
    except Exception as error:
        logger.exception("MCP tool discovery failed url=%s", MCP_SERVER_URL)
        raise MCPConnectionError("MCP tool discovery failed.") from error


def _safe_arguments(arguments: Any) -> str:
    """Serialize tool arguments without logging secret-like values."""

    secret_words = ("token", "secret", "password", "credential", "key")

    def sanitize(value: Any, key: str = "") -> Any:
        if any(word in key.lower() for word in secret_words):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                str(item_key): sanitize(item_value, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    try:
        serialized = json.dumps(sanitize(arguments), default=str)
    except (TypeError, ValueError):
        serialized = repr(arguments)
    return serialized[:2000]


def _content_text(result: Any) -> str:
    return "\n".join(
        item.text
        for item in (getattr(result, "content", None) or [])
        if isinstance(getattr(item, "text", None), str)
    )


def _parse_mcp_result(result: Any) -> Any:
    """Normalize MCP text and structured content without losing tool data."""

    def decode(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    text = _content_text(result)
    if text:
        parsed = decode(text)
        if parsed != text:
            return parsed

        parts = []
        for part in text.splitlines():
            parts.append(decode(part))
        return parts[0] if len(parts) == 1 else parts

    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" in structured:
        structured = decode(structured["result"])
    return structured


def _mcp_failure(result: Any, normalized: Any) -> str | None:
    if bool(getattr(result, "is_error", False)) or bool(
        getattr(result, "isError", False)
    ):
        return _content_text(result) or "The MCP tool reported an error."

    if isinstance(normalized, dict) and normalized.get("success") is False:
        return str(
            normalized.get("error")
            or normalized.get("message")
            or "The MCP tool reported failure."
        )
    return None


async def execute_mcp_tool(
    name: str,
    arguments: dict[str, Any],
) -> dict:
    """Execute an MCP tool and normalize its response."""

    failure = None
    try:
        async with streamable_http_client(MCP_SERVER_URL) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                result = await session.call_tool(
                    name,
                    arguments=arguments,
                )

                normalized_result = _parse_mcp_result(result)
                failure = _mcp_failure(result, normalized_result)
    except MCPToolError:
        raise
    except Exception as error:
        logger.exception("MCP request failed name=%s", name)
        raise MCPConnectionError(f"MCP request for '{name}' failed.") from error

    # Raise after the MCP context managers have exited. Raising inside the
    # SDK's task groups can wrap a tool error in an ExceptionGroup and make it
    # look like a transport failure.
    if failure:
        raise MCPToolError(f"MCP tool '{name}' failed: {failure}")

    return {
        "success": True,
        "result": normalized_result,
    }



async def _chat_with_maddy(
    messages: list[dict[str, Any]],
) -> dict:
    """Run the Bedrock agent with dynamically discovered MCP tools."""

    tools = await discover_mcp_tools()

    if not tools:
        raise RuntimeError("The MCP server exposed no tools.")

    tool_config = {
        "tools": tools,
        "toolChoice": {"auto": {}},
    }

    tool_calls_executed = []

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        try:
            response = converse(
                messages=messages,
                system=(
                    SYSTEM_PROMPT
                    + f"\nCurrent date: {date.today().isoformat()}"
                ),
                tool_config=tool_config,
            )
        except Exception as error:
            logger.exception("Bedrock Converse request failed round=%s", round_number)
            raise BedrockRequestError("Bedrock Converse request failed.") from error

        try:
            assistant_message = response["output"]["message"]
            content = assistant_message.get("content", [])
            stop_reason = response.get("stopReason", "unknown")
        except (KeyError, TypeError, AttributeError) as error:
            logger.exception("Bedrock returned an invalid response")
            raise RuntimeError("Bedrock returned an invalid response.") from error

        messages.append(assistant_message)

        requested_tools = [
            block["toolUse"]
            for block in content
            if isinstance(block, dict) and "toolUse" in block
        ]

        logger.info(
            "Bedrock response round=%s stop_reason=%s requested_tools=%s",
            round_number,
            stop_reason,
            len(requested_tools),
        )

        if not requested_tools:
            if stop_reason == "tool_use":
                logger.error(
                    "Bedrock signaled tool_use without a toolUse block"
                )
                raise RuntimeError(
                    "Bedrock requested a tool but returned no tool request."
                )
            answer = "\n".join(
                block["text"]
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ).strip()

            logger.info("MADDY final assistant response length=%s", len(answer))
            return {
                "answer": answer,
                "reply": answer,
                "tool_calls": tool_calls_executed,
            }

        tool_results = []

        for tool in requested_tools:
            if not isinstance(tool, dict) or not tool.get("toolUseId"):
                raise RuntimeError("Bedrock returned a tool request without toolUseId.")

            name = tool.get("name")
            arguments = tool.get("input", {})
            if not isinstance(name, str) or not name:
                raise RuntimeError("Bedrock returned a tool request without a name.")
            if not isinstance(arguments, dict):
                arguments = {}

            logger.info(
                "Bedrock requested MCP tool name=%s arguments=%s",
                name,
                _safe_arguments(arguments),
            )

            try:
                result = await execute_mcp_tool(
                    name=name,
                    arguments=arguments,
                )

                logger.info(
                    "MCP execution completed name=%s success=%s verified=%s",
                    name,
                    result.get("success"),
                    (result.get("result") or {}).get("verified")
                    if isinstance(result.get("result"), dict)
                    else None,
                )
                tool_calls_executed.append(
                    {"name": name, "success": True, "result": result.get("result")}
                )
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool["toolUseId"],
                            "content": [{"text": json.dumps(result, default=str)}],
                        }
                    }
                )

            except Exception as error:
                logger.exception("MCP tool execution failed name=%s", name)
                error_message = f"{type(error).__name__}: {error}"
                if isinstance(error, MCPConnectionError):
                    error_type = "mcp_unavailable"
                elif isinstance(error, MCPToolError) and name in {
                    "control_smart_device",
                    "get_device_status",
                    "set_device_brightness",
                    "set_device_temperature",
                    "run_automation",
                }:
                    error_type = "smart_home_execution_error"
                elif isinstance(error, MCPToolError):
                    error_type = "mcp_tool_error"
                else:
                    error_type = "tool_execution_error"
                tool_calls_executed.append(
                    {
                        "name": name,
                        "success": False,
                        "error_type": error_type,
                        "error": error_message,
                    }
                )
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool["toolUseId"],
                            "status": "error",
                            "content": [{"text": f"Tool execution failed: {error}"}],
                        }
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    logger.error("MADDY reached maximum tool-calling rounds=%s", MAX_TOOL_ROUNDS)
    raise RuntimeError(
        "MADDY reached the maximum number of tool-calling rounds."
    )


def chat_with_maddy(
    conversation_history: list[dict[str, Any]] | str,
) -> dict:
    """Public synchronous interface used by the FastAPI backend."""

    if isinstance(conversation_history, str):
        user_message = conversation_history.strip()

        if not user_message:
            raise ValueError("Message cannot be empty.")

        messages = [
            {
                "role": "user",
                "content": [{"text": user_message}],
            }
        ]

    else:
        if not conversation_history:
            raise ValueError("Conversation history cannot be empty.")

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

    return anyio.run(_chat_with_maddy, messages)
