import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_URL = "http://127.0.0.1:8001/mcp"


async def main():
    async with streamable_http_client(MCP_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("\n=== AVAILABLE MCP TOOLS ===")
            for tool in tools.tools:
                print(f"\nName: {tool.name}")
                print(f"Description: {tool.description}")
                print(f"Schema: {tool.input_schema}")

            for name, arguments in [
                ("list_tasks", {"include_completed": False}),
                ("get_daily_plan", {}),
            ]:
                print(f"\n=== TESTING {name} ===")

                try:
                    result = await session.call_tool(
                        name,
                        arguments=arguments,
                    )

                    print("Result:", result)
                    print("Result fields:", getattr(result, "model_fields_set", None))

                    for item in getattr(result, "content", []):
                     print(getattr(item, "text", str(item)))

                except Exception as exc:
                    print(f"Exception: {exc!r}")


if __name__ == "__main__":
    asyncio.run(main())
