import asyncio

import pytest

from mcp.types import CallToolResult, TextContent

from app.services import agent_service
from app.services.smart_home_service import control_smart_device


def test_mcp_result_json_and_error_are_normalized():
    success = CallToolResult(
        content=[TextContent(type="text", text='{"success": true, "value": 7}')]
    )
    assert agent_service._parse_mcp_result(success) == {
        "success": True,
        "value": 7,
    }
    assert agent_service._mcp_failure(success, agent_service._parse_mcp_result(success)) is None

    failure = CallToolResult(
        content=[TextContent(type="text", text="device not found")],
        isError=True,
    )
    assert agent_service._mcp_failure(failure, "device not found") == "device not found"

    tool_failure = CallToolResult(
        content=[TextContent(
            type="text",
            text='{"success": false, "error": "Unknown device"}',
        )]
    )
    normalized_failure = agent_service._parse_mcp_result(tool_failure)
    assert agent_service._mcp_failure(tool_failure, normalized_failure) == "Unknown device"

    structured = type("Result", (), {
        "content": [],
        "structuredContent": {"result": '{"success": true, "value": 9}'},
    })()
    assert agent_service._parse_mcp_result(structured) == {
        "success": True,
        "value": 9,
    }


def test_mcp_business_failure_is_not_misclassified_as_transport(monkeypatch):
    failure = CallToolResult(content=[TextContent(
        type="text",
        text='{"success": false, "error": "Unknown device"}',
    )])

    class WrappingContext:
        def __init__(self, value):
            self.value = value

        async def __aenter__(self):
            return self.value

        async def __aexit__(self, exc_type, error, traceback):
            if error is not None:
                raise ExceptionGroup("SDK task group", [error])
            return False

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, error, traceback):
            if error is not None:
                raise ExceptionGroup("SDK task group", [error])
            return False

        async def initialize(self):
            pass

        async def call_tool(self, name, arguments):
            return failure

    monkeypatch.setattr(
        agent_service,
        "streamable_http_client",
        lambda _url: WrappingContext((object(), object())),
    )
    monkeypatch.setattr(agent_service, "ClientSession", lambda *_args: FakeSession())

    with pytest.raises(agent_service.MCPToolError, match="Unknown device"):
        asyncio.run(agent_service.execute_mcp_tool(
            "control_smart_device",
            {"device_id": "missing", "action": "on"},
        ))


def test_smart_home_control_rejects_malformed_arguments():
    try:
        control_smart_device("living_room_light", None)
    except ValueError as error:
        assert str(error) == "Action must be 'on' or 'off'."
    else:
        raise AssertionError("Expected malformed action to be rejected")


def test_smart_home_control_accepts_common_aliases():
    result = control_smart_device("living room lights", "turn on")
    assert result["success"] is True
    assert result["verified"] is True
    assert result["device"]["device_id"] == "living_room_light"
    assert result["device"]["is_on"] is True


def test_bedrock_tool_loop_returns_real_result(monkeypatch):
    responses = iter(
        [
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "tool-1",
                                    "name": "get_device_status",
                                    "input": {"device_id": "living_room_light"},
                                }
                            }
                        ],
                    }
                }
            },
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "The simulated light is off."}],
                    }
                }
            },
        ]
    )
    captured_messages = []

    async def fake_discover():
        return [{"toolSpec": {"name": "get_device_status"}}]

    async def fake_execute(name, arguments):
        assert name == "get_device_status"
        assert arguments == {"device_id": "living_room_light"}
        return {
            "success": True,
            "result": {
                "success": True,
                "mode": "simulation",
                "device": {"device_id": "living_room_light", "is_on": False},
            },
        }

    def fake_converse(messages, **kwargs):
        captured_messages.append(list(messages))
        return next(responses)

    monkeypatch.setattr(agent_service, "discover_mcp_tools", fake_discover)
    monkeypatch.setattr(agent_service, "execute_mcp_tool", fake_execute)
    monkeypatch.setattr(agent_service, "converse", fake_converse)

    result = asyncio.run(
        agent_service._chat_with_maddy(
            [{"role": "user", "content": [{"text": "check the light"}]}]
        )
    )

    assert result["answer"] == "The simulated light is off."
    assert result["tool_calls"][0]["result"]["device"]["is_on"] is False
    assert captured_messages[1][-1]["role"] == "user"
    assert captured_messages[1][-1]["content"][0]["toolResult"]["toolUseId"] == "tool-1"


def test_bedrock_tool_failure_is_reported_to_model(monkeypatch):
    responses = iter(
        [
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "tool-2",
                                    "name": "get_device_status",
                                    "input": {"device_id": "missing"},
                                }
                            }
                        ],
                    }
                }
            },
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "I could not find that device."}],
                    }
                }
            },
        ]
    )
    captured_messages = []

    async def fake_discover():
        return [{"toolSpec": {"name": "get_device_status"}}]

    async def fake_execute(name, arguments):
        raise agent_service.MCPToolError("Unknown device 'missing'")

    def fake_converse(messages, **kwargs):
        captured_messages.append(list(messages))
        return next(responses)

    monkeypatch.setattr(agent_service, "discover_mcp_tools", fake_discover)
    monkeypatch.setattr(agent_service, "execute_mcp_tool", fake_execute)
    monkeypatch.setattr(agent_service, "converse", fake_converse)

    result = asyncio.run(
        agent_service._chat_with_maddy(
            [{"role": "user", "content": [{"text": "check missing"}]}]
        )
    )

    tool_result = captured_messages[1][-1]["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "Unknown device" in tool_result["content"][0]["text"]
    assert result["tool_calls"][0]["success"] is False
    assert result["tool_calls"][0]["error_type"] == "smart_home_execution_error"


def test_bedrock_executes_all_tool_requests_and_correlates_ids(monkeypatch):
    responses = iter([
        {
            "stopReason": "tool_use",
            "output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "first", "name": "control_smart_device",
                              "input": {"device_id": "living_room_light", "action": "on"}}},
                {"toolUse": {"toolUseId": "second", "name": "get_device_status",
                              "input": {"device_id": "living_room_light"}}},
            ]}},
        },
        {"stopReason": "end_turn", "output": {"message": {
            "role": "assistant", "content": [{"text": "The light is on."}]
        }}},
    ])
    tool_result_ids = []

    async def fake_discover():
        return [{"toolSpec": {"name": "control_smart_device"}}]

    async def fake_execute(name, arguments):
        return {"success": True, "result": {"success": True, "name": name}}

    def fake_converse(messages, **kwargs):
        if len(messages) > 1 and messages[-1]["role"] == "user":
            tool_result_ids.extend(
                block["toolResult"]["toolUseId"]
                for block in messages[-1]["content"]
            )
        return next(responses)

    monkeypatch.setattr(agent_service, "discover_mcp_tools", fake_discover)
    monkeypatch.setattr(agent_service, "execute_mcp_tool", fake_execute)
    monkeypatch.setattr(agent_service, "converse", fake_converse)

    result = asyncio.run(agent_service._chat_with_maddy([
        {"role": "user", "content": [{"text": "Turn on the living room light"}]}
    ]))

    assert result["answer"] == "The light is on."
    assert tool_result_ids == ["first", "second"]
    assert len(result["tool_calls"]) == 2


def test_bedrock_tool_use_stop_without_block_is_an_error(monkeypatch):
    async def fake_discover():
        return [{"toolSpec": {"name": "control_smart_device"}}]

    monkeypatch.setattr(agent_service, "discover_mcp_tools", fake_discover)
    monkeypatch.setattr(agent_service, "converse", lambda **kwargs: {
        "stopReason": "tool_use",
        "output": {"message": {"role": "assistant", "content": []}},
    })
    try:
        asyncio.run(agent_service._chat_with_maddy([
            {"role": "user", "content": [{"text": "Turn on the light"}]}
        ]))
    except RuntimeError as error:
        assert "no tool request" in str(error)
    else:
        raise AssertionError("A tool_use stop without a tool block must fail")
