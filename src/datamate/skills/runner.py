"""Bounded child-process execution for application-approved skill scripts."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from datamate.agent.errors import (
    SkillExecutionError,
    SkillOutputError,
    SkillTimeoutError,
    SkillValidationError,
)
from datamate.agent.limits import AgentLimits
from datamate.skills.models import BusinessFile, ScriptObservation, SkillScript
from datamate.skills.registry import SkillRegistry

_READ_MODES = frozenset({"--sheets"})


class SkillRunner:
    """Validate invocations and run trusted scripts with bounded observations."""

    def __init__(self, registry: SkillRegistry, limits: AgentLimits) -> None:
        self._registry = registry
        self._limits = limits

    async def run(
        self,
        *,
        skill_name: str,
        script_name: str,
        argv: Sequence[str],
        business_files: Sequence[BusinessFile],
        workspace: Path,
        timeout_seconds: float | None = None,
    ) -> ScriptObservation:
        """Run one approved script after resolving opaque file handles."""

        script = self._registry.get_script(skill_name, script_name)
        safe_workspace = self._prepare_workspace(workspace)
        resolved_argv = self._validate_invocation(
            script, argv, business_files, safe_workspace
        )
        timeout = min(
            timeout_seconds or self._limits.max_script_seconds,
            self._limits.max_script_seconds,
        )
        return await self._execute(script, resolved_argv, safe_workspace, timeout)

    @staticmethod
    def _prepare_workspace(workspace: Path) -> Path:
        if workspace.is_symlink():
            raise SkillValidationError("Workspace cannot be a symlink")
        workspace.mkdir(parents=True, exist_ok=True)
        resolved = workspace.resolve()
        if not resolved.is_dir():
            raise SkillValidationError("Workspace is unavailable")
        return resolved

    def _validate_invocation(
        self,
        script: SkillScript,
        argv: Sequence[str],
        business_files: Sequence[BusinessFile],
        workspace: Path,
    ) -> list[str]:
        if not argv or any("\x00" in value for value in argv):
            raise SkillValidationError("Invalid skill arguments")
        files = {item.id: item for item in business_files}
        if script.name == "xlsx_read.py":
            return self._validate_xlsx_read(argv, files)
        if script.name == "xlsx_to_csv.py":
            return self._validate_xlsx_to_csv(argv, files, workspace)
        raise SkillValidationError("Script has no invocation policy")

    @staticmethod
    def _xlsx_file(file_id: str, files: dict[str, BusinessFile]) -> Path:
        try:
            item = files[file_id]
        except KeyError as error:
            raise SkillValidationError("Unknown business file") from error
        if item.type != "xlsx" or item.path.is_symlink() or not item.path.is_file():
            raise SkillValidationError("Business file is not an XLSX workbook")
        return item.path.resolve(strict=True)

    def _validate_xlsx_read(
        self, argv: Sequence[str], files: dict[str, BusinessFile]
    ) -> list[str]:
        if len(argv) != 2 or argv[1] not in _READ_MODES:
            raise SkillValidationError("Only bounded workbook inventory is allowed")
        return [str(self._xlsx_file(argv[0], files)), argv[1]]

    def _validate_xlsx_to_csv(
        self,
        argv: Sequence[str],
        files: dict[str, BusinessFile],
        workspace: Path,
    ) -> list[str]:
        if len(argv) < 2:
            raise SkillValidationError("Input and output are required")
        source = self._xlsx_file(argv[0], files)
        output_name = argv[1]
        if Path(output_name).name != output_name or not output_name.endswith(".csv"):
            raise SkillValidationError("Output must be a workspace CSV filename")
        output = (workspace / output_name).resolve()
        if not output.is_relative_to(workspace):
            raise SkillValidationError("Output escapes workspace")

        resolved = [str(source), str(output)]
        index = 2
        while index < len(argv):
            option = argv[index]
            if option == "--data-only":
                resolved.append(option)
                index += 1
                continue
            if option not in {"--sheet", "--encoding", "--delimiter"}:
                raise SkillValidationError("Unsupported conversion option")
            if index + 1 >= len(argv):
                raise SkillValidationError("Conversion option needs a value")
            value = argv[index + 1]
            if option == "--encoding" and value not in {"utf-8", "utf-8-sig"}:
                raise SkillValidationError("Unsupported output encoding")
            if option == "--delimiter" and len(value) != 1:
                raise SkillValidationError("Delimiter must be one character")
            resolved.extend((option, value))
            index += 2
        return resolved

    async def _execute(
        self,
        script: SkillScript,
        argv: Sequence[str],
        workspace: Path,
        timeout: float,
    ) -> ScriptObservation:
        started = time.monotonic()
        environment = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(script.path),
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace,
                env=environment,
                start_new_session=True,
            )
        except OSError as error:
            raise SkillExecutionError("Unable to start skill process") from error

        stdout_task = asyncio.create_task(
            self._read_bounded(process.stdout, self._limits.max_stdout_bytes)
        )
        stderr_task = asyncio.create_task(
            self._read_bounded(process.stderr, self._limits.max_stderr_bytes)
        )
        try:
            async with asyncio.timeout(timeout):
                exit_code = await process.wait()
                stdout_bytes, stdout_truncated = await stdout_task
                stderr_bytes, stderr_truncated = await stderr_task
        except TimeoutError as error:
            self._terminate_process_group(process)
            await process.wait()
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise SkillTimeoutError("Skill execution timed out") from error

        elapsed_ms = round((time.monotonic() - started) * 1000)
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        truncated = stdout_truncated or stderr_truncated
        if exit_code != 0:
            raise SkillExecutionError(
                f"Skill process failed with exit code {exit_code}: {stderr_text}"
            )
        if not stdout_text.strip():
            raise SkillOutputError("Skill returned no output")

        stdout: Any
        try:
            stdout = json.loads(stdout_text)
        except json.JSONDecodeError:
            stdout = stdout_text
        return ScriptObservation(
            ok=True,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr_text,
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    async def _read_bounded(
        stream: asyncio.StreamReader | None, limit: int
    ) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        output = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            remaining = limit - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        return bytes(output), truncated

    @staticmethod
    def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
