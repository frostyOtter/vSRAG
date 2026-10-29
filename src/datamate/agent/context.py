"""Immutable context supplied to an answering agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Resolved question, business, split, and workspace resources."""

    question_id: str
    business_id: str
    question: str
    as_of_date: date
    business_path: Path
    business_readme_path: Path | None
    rulebook_path: Path
    calendar_path: Path
    workspace_path: Path
