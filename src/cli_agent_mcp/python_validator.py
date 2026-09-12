from __future__ import annotations

import shutil
import subprocess  # nosec B404
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from .python_validator_support import VALIDATOR_IGNORED_NAMES, DockerValidatorSupportMixin
from .python_validator_types import CommandRunner, PythonValidationError, ValidatorSettings, is_pinned_image


class DockerPythonValidator(DockerValidatorSupportMixin):
    """Build and start Python code in a short-lived hardened Docker container."""

    def __init__(self, workspace: Path, settings: ValidatorSettings, *, command_runner: CommandRunner = subprocess.run, sleep: Callable[[float], None] = time.sleep) -> None:
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise PythonValidationError(f"Projekt-Workspace existiert nicht: {self.workspace}")
        self.settings = settings
        self._run_command = command_runner
        self._sleep = sleep
        self._container_runner = Path(__file__).with_name("python_validator_container.py").resolve()

    @staticmethod
    def _stage_project(project: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        staging = tempfile.TemporaryDirectory(prefix="cli-agent-validator-")
        staged = Path(staging.name) / "project"
        try:
            shutil.copytree(project, staged, symlinks=True, ignore=shutil.ignore_patterns(*VALIDATOR_IGNORED_NAMES))
        except (OSError, shutil.Error) as exc:
            staging.cleanup()
            raise PythonValidationError("Das Python-Projekt konnte nicht sicher bereitgestellt werden.") from exc
        return staging, staged

    def validate(self, project_path: str, entrypoint: str, *, entrypoint_type: Literal["file", "module"] = "file", arguments: Sequence[str] | None = None, expect_long_running: bool = True) -> dict[str, Any]:
        project = self._resolve_project(project_path)
        self._validate_entrypoint(project, entrypoint, entrypoint_type)
        start_arguments = self._validate_arguments(arguments)
        staging, staged_project = self._stage_project(project)
        container_name = f"cli-agent-python-validator-{uuid.uuid4().hex[:12]}"
        ready_token = f"PYTHON_VALIDATOR_READY_{uuid.uuid4().hex}"
        steps: list[dict[str, Any]] = []
        created = False
        removed = False
        state = None
        logs = ""
        success = False
        try:
            try:
                version = self._command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=10)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                steps.append({"name": "docker_available", "success": False, "detail": str(exc)})
                return self._result(False, project_path, entrypoint, entrypoint_type, start_arguments, expect_long_running, steps, None, "", False)
            docker_ok = version.returncode == 0
            steps.append({"name": "docker_available", "success": docker_ok, "detail": version.stdout.strip() if docker_ok else version.stderr.strip()})
            if not docker_ok:
                return self._result(False, project_path, entrypoint, entrypoint_type, start_arguments, expect_long_running, steps, None, "", False)

            command = [
                "docker", "run", "--detach", "--name", container_name, "--init", "--pull", "never",
                "--user", "65532:65532", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev",
                "--network", self.settings.network_mode, "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--pids-limit", str(self.settings.pids_limit), "--memory", self.settings.memory_limit, "--cpus", self.settings.cpu_limit,
                "--mount", f"type=bind,src={staged_project},dst=/source,readonly",
                "--mount", f"type=bind,src={self._container_runner},dst=/validator/runner.py,readonly",
                "--env", f"PYTHON_VALIDATOR_READY_TOKEN={ready_token}", "--env", "HOME=/tmp/home", "--env", "PYTHONUSERBASE=/tmp/python-user",
                self.settings.python_image, "python", "/validator/runner.py", "--entrypoint-type", entrypoint_type, "--entrypoint", entrypoint, "--", *start_arguments,
            ]
            try:
                started = self._command(command, timeout=self.settings.setup_timeout_seconds)
            except subprocess.TimeoutExpired:
                steps.append({"name": "container_created", "success": False, "detail": "Docker-Start lief in ein Timeout."})
                return self._result(False, project_path, entrypoint, entrypoint_type, start_arguments, expect_long_running, steps, None, "", False)
            created = started.returncode == 0
            steps.append({"name": "container_created", "success": created, "detail": started.stdout.strip() if created else started.stderr.strip()})
            if not created:
                return self._result(False, project_path, entrypoint, entrypoint_type, start_arguments, expect_long_running, steps, None, started.stderr.strip(), False)

            deadline = time.monotonic() + self.settings.setup_timeout_seconds
            ready = False
            while time.monotonic() < deadline:
                logs = self._logs(container_name)
                if any(line.strip() == ready_token for line in logs.splitlines()):
                    ready = True
                    break
                state = self._state(container_name)
                if state and not state.get("Running", False):
                    break
                self._sleep(0.25)
            steps.append({"name": "project_built", "success": ready, "detail": "Projektaufbau abgeschlossen." if ready else "Projektaufbau wurde nicht erfolgreich abgeschlossen."})
            if ready:
                self._sleep(self.settings.startup_grace_seconds)
                state = self._state(container_name)
                logs = self._logs(container_name)
                running = bool(state and state.get("Running", False))
                clean_exit = bool(state and state.get("Status") == "exited" and state.get("ExitCode") == 0)
                success = running or (not expect_long_running and clean_exit)
                steps.append({"name": "process_started", "success": success, "detail": f"Containerstatus={state.get('Status') if state else 'unknown'}"})
        finally:
            try:
                if created:
                    removed, detail = self._remove_container(container_name)
                    steps.append({"name": "container_removed", "success": removed, "detail": detail})
            finally:
                staging.cleanup()
        return self._result(success, project_path, entrypoint, entrypoint_type, start_arguments, expect_long_running, steps, state, logs, removed)

    def _result(self, success: bool, project_path: str, entrypoint: str, entrypoint_type: str, arguments: list[str], expect_long_running: bool, steps: list[dict[str, Any]], state: dict[str, Any] | None, logs: str, container_removed: bool) -> dict[str, Any]:
        return {
            "success": success,
            "project_path": project_path,
            "python_image": self.settings.python_image,
            "validator_policy": {"image_pinned": is_pinned_image(self.settings.python_image), "network_mode": self.settings.network_mode, "source_mount": "sanitized-read-only", "container_user": "65532:65532", "root_filesystem": "read-only"},
            "start": {"entrypoint_type": entrypoint_type, "entrypoint": entrypoint, "argument_count": len(arguments), "expect_long_running": expect_long_running},
            "steps": steps,
            "container_state": state,
            "container_removed": container_removed,
            "logs": logs,
            "scope": "Only dependency installation and process startup were checked; no functional test was executed.",
        }
