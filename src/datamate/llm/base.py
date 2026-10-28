"""LLM client contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from datamate.models import AnswerResult


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Validated input for an answer provider."""

    question_id: str
    business_id: str
    question: str
    as_of_date: date
    business_path: Path


class LLMClient(Protocol):
    """Contract implemented by answer providers."""

    @property
    def provider(self) -> str:
        """Return the provider name used for logs."""

        ...

    async def answer(self, request: LLMRequest) -> AnswerResult:
        """Return one structured answer."""

        ...
