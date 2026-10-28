"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    data_root: Path
    log_level: str
    llm_provider: str
    llm_timeout_seconds: float
    max_question_length: int

    @classmethod
    def from_environment(cls) -> Settings:
        """Build and validate settings from the process environment."""

        timeout = float(os.getenv("DATAMATE_LLM_TIMEOUT_SECONDS", "30"))
        max_length = int(os.getenv("DATAMATE_MAX_QUESTION_LENGTH", "4000"))
        if timeout <= 0:
            raise ValueError("DATAMATE_LLM_TIMEOUT_SECONDS must be positive")
        if max_length <= 0:
            raise ValueError("DATAMATE_MAX_QUESTION_LENGTH must be positive")

        return cls(
            data_root=Path(
                os.getenv("DATAMATE_DATA_ROOT", "data/train/data")
            ).expanduser(),
            log_level=os.getenv("DATAMATE_LOG_LEVEL", "INFO").upper(),
            llm_provider=os.getenv("DATAMATE_LLM_PROVIDER", "placeholder"),
            llm_timeout_seconds=timeout,
            max_question_length=max_length,
        )
