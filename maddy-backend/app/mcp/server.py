import json
import logging

from mcp.server.mcpserver import MCPServer

from app.database.db import initialize_database
from app.services.task_service import (
    complete_task as complete_task_service,
    create_task as create_task_service,
    get_daily_plan as get_daily_plan_service,
    list_tasks as list_tasks_service,
)
from app.services.smart_home_service import (
    initialize_smart_home,
    list_smart_devices as list_smart_devices_service,
    control_smart_device as control_smart_device_service,
    get_device_status as get_device_status_service,
    set_device_brightness as set_device_brightness_service,
    set_device_temperature as set_device_temperature_service,
    run_automation as run_automation_service,
)

logger = logging.getLogger(__name__)

initialize_database()
initialize_smart_home()


mcp = MCPServer(
    name="MADDY",
    instructions=(
        "You are MADDY, a personal AI assistant for productivity "
        "and smart-home management. Use tools for actions rather than "
        "merely describing them. Never claim an action succeeded unless "
        "its tool returns success=true. "
        "For smart-home requests, first resolve the device using "
        "list_smart_devices, then use its exact device_id. "
        "For status requests, use get_device_status. "
        "For lights, use control_smart_device and "
        "set_device_brightness. For thermostats, use "
        "set_device_temperature. For routines, use run_automation. "
        "Available demo automations are goodnight and movie_mode. "
        "Smart-home devices currently operate in SIMULATION mode: "
        "report that simulated state changes do not control real hardware. "
        "For task requests, use the task-management tools. "
        "Never invent devices, automations, or successful results."
    ),
)


def _result(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


# ---------------- TASK MANAGEMENT ----------------

@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: str | None = None,
) -> str:
    """Create a task in MADDY."""
    task = create_task_service(
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
    )
    return _result({
        "success": True,
        "message": "Task created successfully.",
        "task": task,
    })


@mcp.tool()
def list_tasks(include_completed: bool = False) -> str:
    """List MADDY tasks."""
    tasks = list_tasks_service(
        include_completed=include_completed
    )
    return _result({
        "success": True,
        "count": len(tasks),
        "tasks": tasks,
    })


@mcp.tool()
def complete_task(task_id: int) -> str:
    """Mark a task as completed."""
    task = complete_task_service(task_id)
    return _result({
        "success": True,
        "message": "Task completed successfully.",
        "task": task,
    })


@mcp.tool()
def get_daily_plan() -> str:
    """Get a priority-ordered plan for pending tasks."""
    plan = get_daily_plan_service()
    return _result({
        "success": True,
        "daily_plan": plan,
    })


# ---------------- SMART HOME ----------------

@mcp.tool()
def list_smart_devices() -> str:
    """List registered smart-home devices and their current states.

    Devices include their exact device_id, type, room, power state,
    brightness or temperature, and whether they are simulated.
    """
    return _result(list_smart_devices_service())


@mcp.tool()
def control_smart_device(
    device_id: str,
    action: str,
) -> str:
    """Turn a registered simulated smart-home device on or off."""
    try:
        result = control_smart_device_service(device_id, action)
        return _result(result)
    except (ValueError, TypeError) as exc:
        return _result({
            "success": False,
            "error": str(exc),
        })
    except Exception as exc:
        logger.exception(
            "Unexpected smart-home control failure device_id=%s action=%s",
            device_id,
            action,
        )
        return _result({
            "success": False,
            "error": "Smart-home control failed unexpectedly. Check MCP server logs.",
        })



@mcp.tool()
def get_device_status(device_id: str) -> str:
    """Get the current stored state of a registered device."""
    try:
        return _result(
            get_device_status_service(device_id)
        )
    except (ValueError, TypeError) as exc:
        return _result({
            "success": False,
            "error": str(exc),
        })


@mcp.tool()
def set_device_brightness(
    device_id: str,
    brightness: int,
) -> str:
    """Set a registered light's brightness from 0 to 100 percent."""
    try:
        return _result(
            set_device_brightness_service(device_id, brightness)
        )
    except (ValueError, TypeError) as exc:
        return _result({
            "success": False,
            "error": str(exc),
        })


@mcp.tool()
def set_device_temperature(
    device_id: str,
    temperature: float,
) -> str:
    """Set a registered thermostat's target temperature in Celsius."""
    try:
        return _result(
            set_device_temperature_service(device_id, temperature)
        )
    except (ValueError, TypeError) as exc:
        return _result({
            "success": False,
            "error": str(exc),
        })


@mcp.tool()
def run_automation(automation_id: str) -> str:
    """Execute a registered automation.

    Available demo automation IDs:
    - goodnight
    - movie_mode
    """
    try:
        return _result(
            run_automation_service(automation_id)
        )
    except (ValueError, TypeError) as exc:
        return _result({
            "success": False,
            "error": str(exc),
        })


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
        stateless_http=True,
        json_response=True,
    )
