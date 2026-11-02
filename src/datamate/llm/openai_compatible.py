"""OpenAI-compatible Chat Completions transport."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import cast

import httpx
from pydantic import ValidationError

from datamate.agent.errors import (
    ModelResponseError,
    ModelTimeoutError,
    ModelTransportError,
)
from datamate.llm.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    JsonValue,
    ToolCall,
    ToolDefinition,
)

_TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})


class OpenAICompatibleChatModel:
    """Call a local OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        max_response_bytes: int = 1_000_000,
        max_retries: int = 2,
        retry_base_seconds: float = 0.25,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must not be negative")

        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._max_response_bytes = max_response_bytes
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._owns_client = client is None

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def __aenter__(self) -> OpenAICompatibleChatModel:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally managed HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Send a completion request and normalize its first choice."""

        payload = self._serialize_request(request)
        response = await self._post_with_retries(payload)
        try:
            body = await self._read_bounded_body(response)
        except httpx.TimeoutException as error:
            raise ModelTimeoutError("model response timed out") from error
        except httpx.RequestError as error:
            raise ModelTransportError("model response transport failed") from error

        if response.is_error:
            raise ModelTransportError(
                f"model provider returned HTTP {response.status_code}"
            )

        try:
            document = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelResponseError("model provider returned malformed JSON") from error

        return self._parse_response(document)

    async def _post_with_retries(
        self, payload: dict[str, JsonValue]
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                request = self._client.build_request(
                    "POST", self._endpoint, json=payload
                )
                response = await self._client.send(request, stream=True)
            except httpx.TimeoutException as error:
                raise ModelTimeoutError("model request timed out") from error
            except httpx.ConnectError as error:
                if attempt == self._max_retries:
                    raise ModelTransportError("model connection failed") from error
                await self._backoff(attempt)
                continue
            except httpx.RequestError as error:
                raise ModelTransportError("model transport failed") from error

            if (
                response.status_code in _TRANSIENT_STATUS_CODES
                and attempt < self._max_retries
            ):
                await response.aclose()
                await self._backoff(attempt)
                continue
            return response

        raise AssertionError("retry loop must return or raise")

    async def _backoff(self, attempt: int) -> None:
        delay = self._retry_base_seconds * (2**attempt)
        if delay:
            await asyncio.sleep(delay)

    async def _read_bounded_body(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self._max_response_bytes:
                    raise ModelResponseError(
                        "model response exceeds the configured size limit"
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)

    def _serialize_request(self, request: ChatRequest) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "model": self._model,
            "messages": [self._serialize_message(item) for item in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [self._serialize_tool(item) for item in request.tools]
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    def _serialize_message(message: ChatMessage) -> dict[str, JsonValue]:
        serialized: dict[str, JsonValue] = {"role": message.role}
        if message.content is not None:
            serialized["content"] = message.content
        if message.tool_call_id is not None:
            serialized["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            serialized["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        return serialized

    @staticmethod
    def _serialize_tool(tool: ToolDefinition) -> dict[str, JsonValue]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _parse_response(self, document: object) -> ChatResponse:
        root = self._require_mapping(document, "response")
        choices_value = root.get("choices")
        if not isinstance(choices_value, list) or not choices_value:
            raise ModelResponseError("model response has no choices")
        choices = cast(list[object], choices_value)

        choice = self._require_mapping(choices[0], "choice")
        message = self._require_mapping(choice.get("message"), "choice message")

        content_value = message.get("content")
        if content_value is not None and not isinstance(content_value, str):
            raise ModelResponseError("model response content must be a string or null")

        raw_tool_calls_value = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls_value, list):
            raise ModelResponseError("model response tool_calls must be a list")
        raw_tool_calls = cast(list[object], raw_tool_calls_value)
        tool_calls = [self._parse_tool_call(item) for item in raw_tool_calls]

        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ModelResponseError("model finish_reason must be a string or null")
        if content_value is None and not tool_calls:
            raise ModelResponseError("model response contains no content or tool calls")

        try:
            return ChatResponse(
                content=content_value,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        except ValidationError as error:
            raise ModelResponseError("model response failed validation") from error

    def _parse_tool_call(self, value: object) -> ToolCall:
        item = self._require_mapping(value, "tool call")
        call_id = item.get("id")
        call_type = item.get("type")
        if call_type is not None and call_type != "function":
            raise ModelResponseError("tool call type must be function")
        function = self._require_mapping(item.get("function"), "tool function")
        name = function.get("name")
        raw_arguments = function.get("arguments")

        if not isinstance(call_id, str) or not call_id:
            raise ModelResponseError("tool call id must be a non-empty string")
        if not isinstance(name, str) or not name:
            raise ModelResponseError("tool call name must be a non-empty string")
        if not isinstance(raw_arguments, str):
            raise ModelResponseError("tool call arguments must be a JSON string")

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            raise ModelResponseError("tool call arguments contain malformed JSON") from error
        if not isinstance(arguments, dict):
            raise ModelResponseError("tool call arguments must decode to an object")

        try:
            return ToolCall(
                id=call_id,
                name=name,
                arguments=cast(dict[str, JsonValue], arguments),
            )
        except ValidationError as error:
            raise ModelResponseError("tool call arguments failed validation") from error

    @staticmethod
    def _require_mapping(value: object, label: str) -> Mapping[str, object]:
        if not isinstance(value, dict):
            raise ModelResponseError(f"model {label} must be an object")
        return cast(Mapping[str, object], value)
