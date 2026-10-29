"""Deterministic placeholder answer provider."""

from __future__ import annotations

from datamate.agent.base import LLMRequest
from datamate.answer_contract import AnswerResult, StringAnswer


class PlaceholderLLMClient:
    """Return fake answers until a real local model is connected."""

    @property
    def provider(self) -> str:
        """Return the provider name."""

        return "placeholder"

    async def answer(self, request: LLMRequest) -> AnswerResult:
        """Return a deterministic placeholder result."""

        return StringAnswer(
            type="string",
            answer=f"Placeholder answer for {request.business_id}",
        )
