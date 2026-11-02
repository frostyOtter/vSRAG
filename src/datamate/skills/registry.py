"""Safe discovery and lookup of root-level runtime skills."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from datamate.agent.errors import SkillNotFoundError, SkillValidationError
from datamate.skills.models import (
    ScriptCapability,
    Skill,
    SkillReference,
    SkillScript,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SUPPORTED_REFERENCES = frozenset({".md", ".txt", ".json", ".csv"})
_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)

# Metadata never grants execution. Every runnable script must appear here.
DEFAULT_SCRIPT_POLICY: Mapping[tuple[str, str], ScriptCapability] = MappingProxyType(
    {
        ("xlsx", "xlsx_read.py"): ScriptCapability.READ_ONLY,
        ("xlsx", "xlsx_to_csv.py"): ScriptCapability.WORKSPACE_WRITE,
    }
)


def _regular_safe_file(path: Path, root: Path) -> bool:
    """Return whether path is a non-symlink regular file below root."""

    if path.is_symlink() or not path.is_file():
        return False
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse the scalar metadata required by the skill contract."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SkillValidationError("Unable to read skill instructions") from error
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        raise SkillValidationError("SKILL.md must begin with YAML frontmatter")

    metadata: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line[0].isspace():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            raise SkillValidationError("Invalid SKILL.md frontmatter")
        clean_value = value.strip()
        if clean_value and clean_value[0] in "[{":
            continue
        metadata[key.strip()] = clean_value.strip('"\'')
    return metadata


class SkillRegistry:
    """Immutable registry built from validated direct child directories."""

    def __init__(self, skills: Mapping[str, Skill]) -> None:
        self._skills = MappingProxyType(dict(skills))

    @classmethod
    def discover(
        cls,
        roots: Iterable[Path],
        *,
        script_policy: Mapping[tuple[str, str], ScriptCapability] | None = None,
    ) -> SkillRegistry:
        """Discover skills without following symlinks or nested skill roots."""

        policy = script_policy if script_policy is not None else DEFAULT_SCRIPT_POLICY
        skills: dict[str, Skill] = {}
        for configured_root in roots:
            if configured_root.is_symlink():
                raise SkillValidationError("Skill root cannot be a symlink")
            root = configured_root.resolve()
            if not root.is_dir():
                raise SkillValidationError("Skill root is unavailable")
            for directory in sorted(root.iterdir(), key=lambda item: item.name):
                if directory.is_symlink():
                    raise SkillValidationError("Symlinked skill directories are forbidden")
                if not directory.is_dir():
                    continue
                skill = cls._discover_skill(directory.resolve(), root, policy)
                if skill.name in skills:
                    raise SkillValidationError(f"Duplicate skill name: {skill.name}")
                skills[skill.name] = skill
        return cls(skills)

    @staticmethod
    def _discover_skill(
        directory: Path,
        root: Path,
        policy: Mapping[tuple[str, str], ScriptCapability],
    ) -> Skill:
        try:
            directory.relative_to(root)
        except ValueError as error:
            raise SkillValidationError("Skill path escapes configured root") from error
        instructions = directory / "SKILL.md"
        if not _regular_safe_file(instructions, directory):
            raise SkillValidationError("Skill must contain a safe SKILL.md")
        metadata = _parse_frontmatter(instructions)
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        if not _NAME_PATTERN.fullmatch(name):
            raise SkillValidationError("Skill name is invalid")
        if not description or len(description) > 500:
            raise SkillValidationError("Skill description is invalid")

        scripts: dict[str, SkillScript] = {}
        scripts_directory = directory / "scripts"
        if scripts_directory.exists():
            if scripts_directory.is_symlink() or not scripts_directory.is_dir():
                raise SkillValidationError("Skill scripts path is unsafe")
            for path in sorted(scripts_directory.iterdir(), key=lambda item: item.name):
                if path.is_symlink():
                    raise SkillValidationError("Symlinked skill scripts are forbidden")
                if path.suffix != ".py" or not _regular_safe_file(path, directory):
                    continue
                capability = policy.get((name, path.name))
                if capability is not None:
                    scripts[path.name] = SkillScript(path.name, path, capability)

        references: dict[str, SkillReference] = {}
        references_directory = directory / "references"
        if references_directory.exists():
            if references_directory.is_symlink() or not references_directory.is_dir():
                raise SkillValidationError("Skill references path is unsafe")
            for path in sorted(references_directory.iterdir(), key=lambda item: item.name):
                if path.is_symlink():
                    raise SkillValidationError("Symlinked skill references are forbidden")
                if (
                    path.suffix.lower() in _SUPPORTED_REFERENCES
                    and _regular_safe_file(path, directory)
                ):
                    references[path.name] = SkillReference(path.name, path)

        return Skill(
            name=name,
            description=description,
            version=metadata.get("version") or None,
            path=directory,
            instructions_path=instructions,
            scripts=Skill.immutable_resources(scripts),
            references=Skill.immutable_resources(references),
        )

    def list(self) -> tuple[Skill, ...]:
        """Return registered skills in deterministic name order."""

        return tuple(self._skills[name] for name in sorted(self._skills))

    def get(self, name: str) -> Skill:
        """Return one registered skill without exposing host paths in errors."""

        try:
            return self._skills[name]
        except KeyError as error:
            raise SkillNotFoundError(f"Unknown skill: {name}") from error

    def get_script(self, skill_name: str, script_name: str) -> SkillScript:
        """Return an approved script, never merely a discovered candidate."""

        try:
            return self.get(skill_name).scripts[script_name]
        except KeyError as error:
            raise SkillNotFoundError("Unknown or disabled skill script") from error

    def get_reference(self, skill_name: str, reference_name: str) -> SkillReference:
        """Return a safe registered reference document."""

        try:
            return self.get(skill_name).references[reference_name]
        except KeyError as error:
            raise SkillNotFoundError("Unknown skill reference") from error
