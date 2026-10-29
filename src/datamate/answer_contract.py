"""Strict DataMate final-answer contract."""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type JsonScalar = str | int | float | bool | None
type FiniteNumber = int | float


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and coerced values."""

    model_config = ConfigDict(extra="forbid", strict=True)


def _ensure_finite(value: int | float) -> int | float:
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("answer must be a finite number")
    return value


class NumberAnswer(StrictModel):
    """Numeric answer, including monetary amounts and counts."""

    type: Literal["number"]
    answer: FiniteNumber

    _validate_answer = field_validator("answer")(_ensure_finite)


class PercentAnswer(StrictModel):
    """Percentage value expressed as a number, without a percent sign."""

    type: Literal["percent"]
    answer: FiniteNumber

    _validate_answer = field_validator("answer")(_ensure_finite)


class DateAnswer(StrictModel):
    """Date answer in YYYY-MM-DD or YYYY-MM form."""

    type: Literal["date"]
    answer: str

    @field_validator("answer")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        """Reject non-canonical and impossible calendar dates."""

        if len(value) == 7:
            try:
                year_text, month_text = value.split("-")
                year = int(year_text)
                month = int(month_text)
                if len(year_text) != 4 or len(month_text) != 2:
                    raise ValueError
                date(year, month, 1)
            except ValueError as error:
                raise ValueError("answer must be a valid YYYY-MM date") from error
            return value

        if len(value) == 10:
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("answer must be a valid YYYY-MM-DD date") from error
            if parsed.isoformat() != value:
                raise ValueError("answer must use canonical YYYY-MM-DD format")
            return value

        raise ValueError("answer must use YYYY-MM-DD or YYYY-MM format")


class BooleanAnswer(StrictModel):
    """Boolean answer."""

    type: Literal["boolean"]
    answer: bool


class StringAnswer(StrictModel):
    """String answer copied from the released data."""

    type: Literal["string"]
    answer: str


class ListAnswer(StrictModel):
    """Ordered list answer containing JSON scalar values."""

    type: Literal["list"]
    answer: list[JsonScalar]

    @field_validator("answer")
    @classmethod
    def validate_values(cls, values: list[JsonScalar]) -> list[JsonScalar]:
        """Reject non-finite numbers in list answers."""

        for value in values:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("list values must be finite")
        return values


class TableValue(StrictModel):
    """Tabular answer payload."""

    columns: list[str]
    rows: list[list[JsonScalar]]

    @model_validator(mode="after")
    def validate_rows(self) -> TableValue:
        """Require rectangular rows with only finite numeric values."""

        column_count = len(self.columns)
        for row in self.rows:
            if len(row) != column_count:
                raise ValueError("each table row must match the column count")
            for value in row:
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("table values must be finite")
        return self


class TableAnswer(StrictModel):
    """Table answer."""

    type: Literal["table"]
    answer: TableValue


class UnanswerableAnswer(StrictModel):
    """Answer used when released data cannot support the question."""

    type: Literal["unanswerable"]
    reason: str | None = None


class AbstainAnswer(StrictModel):
    """Answer used when the agent chooses not to answer."""

    type: Literal["abstain"]


type AnswerResult = Annotated[
    NumberAnswer
    | PercentAnswer
    | DateAnswer
    | BooleanAnswer
    | StringAnswer
    | ListAnswer
    | TableAnswer
    | UnanswerableAnswer
    | AbstainAnswer,
    Field(discriminator="type"),
]
