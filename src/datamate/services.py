"""Question answering orchestration."""

from __future__ import annotations

import asyncio

from datamate.business_store import BusinessStore
from datamate.llm.base import LLMClient, LLMRequest
from datamate.models import AnswerRequest, AnswerResponse


class LLMTimeoutError(Exception):
    """Raised when the answer provider exceeds its deadline."""


class LLMClientError(Exception):
    """Raised when the answer provider fails."""


class AnswerService:
    """Check business data and ask the configured answer provider."""

    def __init__(
        self,
        business_store: BusinessStore,
        llm_client: LLMClient,
        timeout_seconds: float,
    ) -> None:
        self.business_store = business_store
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds

    async def answer(self, request: AnswerRequest) -> AnswerResponse:
        """Produce one answer for a validated API request."""

        business_path = self.business_store.resolve(request.business_id)
        llm_request = LLMRequest(
            question_id=request.id,
            business_id=request.business_id,
            question=request.question,
            as_of_date=request.as_of_date,
            business_path=business_path,
        )

        try:
            result = await asyncio.wait_for(
                self.llm_client.answer(llm_request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise LLMTimeoutError from error
        except Exception as error:
            raise LLMClientError from error

        return AnswerResponse(
            id=request.id,
            business_id=request.business_id,
            result=result,
        )
