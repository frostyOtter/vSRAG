"""Model-independent chat and tool-call contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class StrictModel(BaseModel):
    """Base model for validated provider-independent messages."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ChatMessage(StrictModel):
    """One message sent to or received from a chat model."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None


class ToolDefinition(StrictModel):
    """JSON-schema definition of one callable model tool."""

    name: str
    description: str
    parameters: dict[str, JsonValue]


class ToolCall(StrictModel):
    """One structured tool request emitted by a model."""

    id: str
    name: str
    arguments: dict[str, JsonValue]


def _empty_tool_definitions() -> list[ToolDefinition]:
    return []


def _empty_tool_calls() -> list[ToolCall]:
    return []


class ChatRequest(StrictModel):
    """Provider-independent chat completion request."""

    messages: list[ChatMessage]
    tools: list[ToolDefinition] = Field(default_factory=_empty_tool_definitions)
    temperature: float = 0.0
    max_tokens: int | None = None


class ChatResponse(StrictModel):
    """Provider-independent chat completion response."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=_empty_tool_calls)
    finish_reason: str | None = None
