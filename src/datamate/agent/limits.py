"""Hard limits for one agent request."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Budgets enforced by the agent loop and execution tools."""

    max_steps: int = 8
    max_tool_calls: int = 6
    max_model_calls: int = 8
    max_wall_seconds: float = 120.0
    max_script_seconds: float = 20.0
    max_script_source_bytes: int = 50_000
    max_tool_output_bytes: int = 100_000
    max_observation_chars: int = 40_000
    max_stdout_bytes: int = 100_000
    max_stderr_bytes: int = 20_000

    def __post_init__(self) -> None:
        """Reject non-positive limits at configuration boundaries."""

        for field_name in self.__dataclass_fields__:
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
