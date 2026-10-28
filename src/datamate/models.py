"""HTTP and answer data models."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BusinessId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]
AnswerType = Literal[
    "number",
    "percent",
    "date",
    "boolean",
    "string",
    "list",
    "table",
    "unanswerable",
    "abstain",
]
AnswerValue = str | int | float | bool | list[object] | dict[str, object] | None


class StrictModel(BaseModel):
    """Base model that rejects unexpected input fields."""

    model_config = ConfigDict(extra="forbid")


class AnswerRequest(StrictModel):
    """One user question."""

    id: Annotated[str, Field(min_length=1)]
    business_id: BusinessId
    question: Annotated[str, Field(min_length=1)]
    as_of_date: date


class AnswerResult(StrictModel):
    """DataMate-shaped answer returned by an LLM client."""

    type: AnswerType
    answer: AnswerValue = None
    reason: str | None = None


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
