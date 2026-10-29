"""Chat model protocol."""

from __future__ import annotations

from typing import Protocol

from datamate.llm.models import ChatRequest, ChatResponse


class ChatModel(Protocol):
    """Provider-independent contract implemented by chat model adapters."""

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Return one model completion for a validated request."""

        ...
