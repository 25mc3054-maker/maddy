import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "http://127.0.0.1:8001/mcp"


def print_result(result):
    """Print text and structured content returned by an MCP tool."""

    for item in getattr(result, "content", []):
        if hasattr(item, "text"):
            print(item.text)

    # Correct field name for the installed MCP SDK
    structured = getattr(result, "structured_content", None)

    if structured is not None:
        print(json.dumps(structured, indent=2, default=str))

    # Correct field name: is_error, not isError
    if getattr(result, "is_error", False):
        raise RuntimeError("The MCP tool reported an error.")


async def main():
    async with streamable_http_client(MCP_URL) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            print("\n=== 1. Connected to MADDY MCP ===")

            print("\n=== 2. Discovering available tools ===")
            response = await session.list_tools()

            for tool in response.tools:
                print(f"- {tool.name}: {tool.description}")

            available_tools = {
                tool.name for tool in response.tools
            }

            required_tools = {
                "create_task",
                "list_tasks",
                "complete_task",
                "get_daily_plan",
            }

            missing = required_tools - available_tools

            if missing:
                raise RuntimeError(
                    f"Missing MCP tools: {sorted(missing)}"
                )

            print("\nAll four expected tools are available.")

            print("\n=== 3. Creating a test task ===")
            created = await session.call_tool(
                "create_task",
                arguments={
                    "title": "Test MADDY MCP integration",
                    "description": "Created through the MCP protocol",
                    "priority": "high",
                },
            )
            print_result(created)

            print("\n=== 4. Listing pending tasks ===")
            listed = await session.call_tool(
                "list_tasks",
                arguments={"include_completed": False},
            )
            print_result(listed)

            print("\n=== 5. Generating a daily plan ===")
            plan = await session.call_tool(
                "get_daily_plan",
                arguments={},
            )
            print_result(plan)

            print("\n=== 6. MCP integration smoke test finished ===")
            print("Check the output above for errors and successful results.")


if __name__ == "__main__":
    asyncio.run(main())
