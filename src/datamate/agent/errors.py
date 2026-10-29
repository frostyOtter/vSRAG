"""Internal agent, model, and skill exception hierarchy."""

from __future__ import annotations


class AgentError(Exception):
    """Base class for errors raised while producing an agent answer."""


class AgentProtocolError(AgentError):
    """Raised when model output violates the agent protocol."""


class AgentLimitExceededError(AgentError):
    """Raised when a request exhausts an enforced agent budget."""


class InvalidFinalAnswerError(AgentProtocolError):
    """Raised when final-answer arguments violate the answer contract."""


class ModelError(AgentError):
    """Base class for model transport or response failures."""


class ModelTimeoutError(ModelError):
    """Raised when a model call exceeds its deadline."""


class ModelTransportError(ModelError):
    """Raised when communication with the model provider fails."""


class ModelResponseError(ModelError):
    """Raised when a provider returns an invalid response."""


class SkillError(AgentError):
    """Base class for skill discovery and execution failures."""


class SkillNotFoundError(SkillError):
    """Raised when a requested skill resource is not registered."""


class SkillValidationError(SkillError):
    """Raised when a skill or invocation fails validation."""


class SkillExecutionError(SkillError):
    """Raised when a skill process fails."""


class SkillTimeoutError(SkillExecutionError):
    """Raised when a skill exceeds its execution deadline."""


class SkillOutputError(SkillExecutionError):
    """Raised when skill output is malformed or exceeds its bounds."""
