"""Explicit, bounded access to business and split resources."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from datamate.agent.context import AgentContext
from datamate.agent.errors import SkillOutputError, SkillValidationError
from datamate.skills.models import BusinessFile

_SUPPORTED_BUSINESS_FILES = frozenset({".csv", ".xlsx", ".sqlite", ".db"})


def list_business_files(business_path: Path) -> tuple[BusinessFile, ...]:
    """Build deterministic opaque handles for safe direct business files."""

    root = business_path.resolve(strict=True)
    files: list[BusinessFile] = []
    candidates = sorted(root.iterdir(), key=lambda item: item.name)
    for path in candidates:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.lower() not in _SUPPORTED_BUSINESS_FILES
        ):
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            continue
        files.append(
            BusinessFile(
                id=f"file_{len(files) + 1}",
                relative_path=path.name,
                type=path.suffix.lower().lstrip("."),
                size_bytes=path.stat().st_size,
                path=resolved,
            )
        )
    return tuple(files)


def read_context_document(
    context: AgentContext, document: str, *, max_bytes: int
) -> str:
    """Read one allowlisted context document with a hard byte bound."""

    paths = {
        "business_readme": context.business_readme_path,
        "rulebook": context.rulebook_path,
        "calendar": context.calendar_path,
    }
    if document not in paths:
        raise SkillValidationError("Unknown context document")
    path = paths[document]
    if path is None or path.is_symlink() or not path.is_file():
        raise SkillValidationError("Context document is unavailable")
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise SkillOutputError("Context document exceeds output limit")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SkillOutputError("Context document is not valid UTF-8") from error


def inspect_sqlite(
    business_file: BusinessFile,
    *,
    sample_rows: int = 5,
    max_output_bytes: int = 100_000,
) -> dict[str, object]:
    """Return schemas, counts, and bounded samples from a read-only database."""

    if business_file.type not in {"sqlite", "db"}:
        raise SkillValidationError("Business file is not SQLite")
    if not 0 <= sample_rows <= 20:
        raise SkillValidationError("sample_rows must be between 0 and 20")
    uri = f"file:{business_file.path.as_posix()}?mode=ro&immutable=1"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        result: list[dict[str, object]] = []
        for table in tables:
            name = str(table["name"])
            quoted = name.replace('"', '""')
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted}"'  # noqa: S608
            ).fetchone()[0]
            samples = [
                dict(row)
                for row in connection.execute(
                    f'SELECT * FROM "{quoted}" LIMIT ?',  # noqa: S608
                    (sample_rows,),
                ).fetchall()
            ]
            result.append(
                {
                    "name": name,
                    "schema": table["sql"],
                    "row_count": count,
                    "sample": samples,
                }
            )
    except sqlite3.Error as error:
        raise SkillOutputError("Unable to inspect SQLite database") from error
    finally:
        if connection is not None:
            connection.close()

    output: dict[str, object] = {"tables": result}
    try:
        encoded = json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SkillOutputError("SQLite sample cannot be serialized") from error
    if len(encoded) > max_output_bytes:
        raise SkillOutputError("SQLite inspection exceeds output limit")
    return output


def inspect_csv(
    business_file: BusinessFile, *, sample_rows: int = 5
) -> dict[str, object]:
    """Return a small UTF-8 CSV schema/sample without loading the full file."""

    if business_file.type != "csv":
        raise SkillValidationError("Business file is not CSV")
    try:
        with business_file.path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            rows = [row for _, row in zip(range(sample_rows + 1), reader, strict=False)]
    except (OSError, UnicodeError, csv.Error) as error:
        raise SkillOutputError("Unable to inspect CSV") from error
    return {"rows": rows}
