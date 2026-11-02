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
    llm_base_url: str = "http://localhost:8000/v1"
    llm_api_key: str | None = None
    llm_model: str = "Qwen3-14B"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    llm_max_response_bytes: int = 1_000_000
    llm_max_retries: int = 2

    @classmethod
    def from_environment(cls) -> Settings:
        """Build and validate settings from the process environment."""

        timeout = float(os.getenv("DATAMATE_LLM_TIMEOUT_SECONDS", "30"))
        max_length = int(os.getenv("DATAMATE_MAX_QUESTION_LENGTH", "4000"))
        temperature = float(os.getenv("DATAMATE_LLM_TEMPERATURE", "0"))
        max_tokens = int(os.getenv("DATAMATE_LLM_MAX_TOKENS", "4096"))
        max_response_bytes = int(
            os.getenv("DATAMATE_LLM_MAX_RESPONSE_BYTES", "1000000")
        )
        max_retries = int(os.getenv("DATAMATE_LLM_MAX_RETRIES", "2"))
        if timeout <= 0:
            raise ValueError("DATAMATE_LLM_TIMEOUT_SECONDS must be positive")
        if max_length <= 0:
            raise ValueError("DATAMATE_MAX_QUESTION_LENGTH must be positive")
        if max_tokens <= 0:
            raise ValueError("DATAMATE_LLM_MAX_TOKENS must be positive")
        if max_response_bytes <= 0:
            raise ValueError("DATAMATE_LLM_MAX_RESPONSE_BYTES must be positive")
        if max_retries < 0:
            raise ValueError("DATAMATE_LLM_MAX_RETRIES must not be negative")

        api_key = os.getenv("DATAMATE_LLM_API_KEY") or None
        return cls(
            data_root=Path(
                os.getenv("DATAMATE_DATA_ROOT", "data/train/data")
            ).expanduser(),
            log_level=os.getenv("DATAMATE_LOG_LEVEL", "INFO").upper(),
            llm_provider=os.getenv("DATAMATE_LLM_PROVIDER", "placeholder"),
            llm_timeout_seconds=timeout,
            max_question_length=max_length,
            llm_base_url=os.getenv(
                "DATAMATE_LLM_BASE_URL", "http://localhost:8000/v1"
            ),
            llm_api_key=api_key,
            llm_model=os.getenv("DATAMATE_LLM_MODEL", "Qwen3-14B"),
            llm_temperature=temperature,
            llm_max_tokens=max_tokens,
            llm_max_response_bytes=max_response_bytes,
            llm_max_retries=max_retries,
        )
