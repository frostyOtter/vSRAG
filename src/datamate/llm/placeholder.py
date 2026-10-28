"""Deterministic placeholder answer provider."""

from __future__ import annotations

from datamate.llm.base import LLMRequest
from datamate.models import AnswerResult


class PlaceholderLLMClient:
    """Return fake answers until a real local model is connected."""

    @property
    def provider(self) -> str:
        """Return the provider name."""

        return "placeholder"

    async def answer(self, request: LLMRequest) -> AnswerResult:
        """Return a deterministic placeholder result."""

        return AnswerResult(
            type="string",
            answer=f"Placeholder answer for {request.business_id}",
        )
