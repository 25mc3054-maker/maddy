import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.database.db import initialize_database
from app.services.agent_service import (
    BedrockRequestError,
    MCPConnectionError,
    chat_with_maddy,
)
from fastapi.middleware.cors import CORSMiddleware
from app.services.task_service import (
    complete_task,
    create_task,
    get_daily_plan,
    list_tasks,
)
from app.services.memory_service import (
    add_message,
    get_history,
)
from app.services.smart_home_service import (
    initialize_smart_home,
    list_smart_devices,
    get_device_status,
    control_smart_device,
    set_device_brightness,
    set_device_temperature,
    run_automation,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    initialize_smart_home()
    yield


app = FastAPI(
    title="MADDY Personal AI",
    description=(
        "A personal AI assistant for tasks, home management, "
        "and professional workflows."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.47.93:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_date: str | None = None

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "application": "MADDY",
    }


@app.get("/api/tasks")
def get_tasks(include_completed: bool = False):
    return {
        "tasks": list_tasks(include_completed=include_completed)
    }


@app.post("/api/tasks", status_code=201)
def add_task(task: TaskCreate):
    try:
        return create_task(
            title=task.title,
            description=task.description,
            priority=task.priority,
            due_date=task.due_date,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.post("/api/tasks/{task_id}/complete")
def mark_task_complete(task_id: int):
    try:
        return complete_task(task_id)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@app.get("/api/daily-plan")
def daily_plan():
    return get_daily_plan()

@app.post("/api/chat")
def chat(request: ChatRequest):
    conversation_id = request.conversation_id or str(uuid4())
    logger.info(
        "Chat request received conversation_id=%s message_length=%s",
        conversation_id,
        len(request.message),
    )

    history = get_history(conversation_id)

    history.append({
        "role": "user",
        "content": [{"text": request.message}],
    })

    try:
        result = chat_with_maddy(history)

        answer = result["answer"]

        add_message(
            conversation_id,
            {
                "role": "user",
                "content": [{"text": request.message}],
            },
        )

        add_message(
            conversation_id,
            {
                "role": "assistant",
                "content": [{"text": answer}],
            },
        )

        logger.info(
            "Chat response completed conversation_id=%s tool_calls=%s answer_length=%s",
            conversation_id,
            len(result.get("tool_calls", [])),
            len(answer),
        )

        return {
            "conversation_id": conversation_id,
            "answer": answer,
            "tool_calls": result.get("tool_calls", []),
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except MCPConnectionError:
        logger.exception("MADDY chat request failed during MCP communication")
        return JSONResponse(
            status_code=503,
            content={
                "error_type": "mcp_unavailable",
                "detail": "MADDY could not reach the MCP server. Check server logs.",
            },
        )

    except BedrockRequestError:
        logger.exception("MADDY chat request failed during Bedrock inference")
        return JSONResponse(
            status_code=502,
            content={
                "error_type": "bedrock_error",
                "detail": "MADDY could not get a response from Bedrock. Check server logs.",
            },
        )

    except Exception:
        logger.exception("MADDY chat request failed")

        return JSONResponse(
            status_code=502,
            content={
                "error_type": "agent_error",
                "detail": "MADDY could not complete the AI request. Check server logs.",
            },
        )


# ---------------- SMART HOME API ----------------

class DeviceControlRequest(BaseModel):
    action: Literal["on", "off"]


class BrightnessRequest(BaseModel):
    brightness: int = Field(ge=0, le=100)


class TemperatureRequest(BaseModel):
    temperature: float = Field(ge=5, le=35)


@app.get("/api/smart-home/devices")
def get_smart_devices():
    return list_smart_devices()


@app.get("/api/smart-home/devices/{device_id}")
def get_smart_device(device_id: str):
    try:
        return get_device_status(device_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/smart-home/devices/{device_id}/control")
def control_device(device_id: str, request: DeviceControlRequest):
    try:
        return control_smart_device(device_id, request.action)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/smart-home/devices/{device_id}/brightness")
def update_device_brightness(device_id: str, request: BrightnessRequest):
    try:
        return set_device_brightness(device_id, request.brightness)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/smart-home/devices/{device_id}/temperature")
def update_device_temperature(device_id: str, request: TemperatureRequest):
    try:
        return set_device_temperature(device_id, request.temperature)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/smart-home/automations/{automation_id}/run")
def execute_smart_home_automation(automation_id: str):
    try:
        return run_automation(automation_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
