"""Immutable contracts for discovered skills and bounded execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class ScriptCapability(StrEnum):
    """Security-relevant behavior assigned by application policy."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    BUSINESS_MUTATION = "business_mutation"
    EXTERNAL_PROCESS = "external_process"


@dataclass(frozen=True, slots=True)
class SkillScript:
    """One discovered script with an application-owned capability."""

    name: str
    path: Path
    capability: ScriptCapability


@dataclass(frozen=True, slots=True)
class SkillReference:
    """One bounded reference document belonging to a skill."""

    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class Skill:
    """Validated skill metadata and resources."""

    name: str
    description: str
    version: str | None
    path: Path
    instructions_path: Path
    scripts: Mapping[str, SkillScript]
    references: Mapping[str, SkillReference]

    @staticmethod
    def immutable_resources[T](resources: dict[str, T]) -> Mapping[str, T]:
        """Return a read-only snapshot of a discovered resource mapping."""

        return MappingProxyType(dict(resources))


@dataclass(frozen=True, slots=True)
class BusinessFile:
    """Opaque model-facing handle for one business data file."""

    id: str
    relative_path: str
    type: str
    size_bytes: int
    path: Path


@dataclass(frozen=True, slots=True)
class ScriptObservation:
    """Normalized result from an approved child process."""

    ok: bool
    exit_code: int
    stdout: object
    stderr: str
    truncated: bool
    elapsed_ms: int
