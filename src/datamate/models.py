"""HTTP and answer data models."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from datamate.answer_contract import AnswerResult

BusinessId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]


class StrictModel(BaseModel):
    """Base model that rejects unexpected input fields."""

    model_config = ConfigDict(extra="forbid")


class AnswerRequest(StrictModel):
    """One user question."""

    id: Annotated[str, Field(min_length=1)]
    business_id: BusinessId
    question: Annotated[str, Field(min_length=1)]
    as_of_date: date


class AnswerResponse(StrictModel):
    """Successful API response."""

    id: str
    business_id: str
    result: AnswerResult


class ErrorBody(StrictModel):
    """Stable API error body."""

    code: str
    message: str


class ErrorResponse(StrictModel):
    """Error response envelope."""

    error: ErrorBody


class StatusResponse(StrictModel):
    """Health endpoint response."""

    status: str
