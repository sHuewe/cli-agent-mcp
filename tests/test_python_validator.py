import subprocess
from pathlib import Path

import pytest

from cli_agent_mcp.python_validator import DockerPythonValidator
from cli_agent_mcp.python_validator_types import PythonValidationError, ValidatorSettings, is_pinned_image

PINNED_IMAGE = "registry.internal/python@sha256:" + "a" * 64


def test_pinned_image_policy() -> None:
    assert is_pinned_image(PINNED_IMAGE)
    assert not is_pinned_image("registry.internal/python:latest")
    with pytest.raises(ValueError, match="sha256-Digest"):
        ValidatorSettings(python_image="registry.internal/python:latest")


def test_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    validator = DockerPythonValidator(tmp_path, ValidatorSettings(python_image=PINNED_IMAGE))
    with pytest.raises(PythonValidationError, match="relativ"):
        validator.validate(str(tmp_path), "main.py")
    with pytest.raises(PythonValidationError, match=r"\.\."):
        validator.validate("../other", "main.py")


def test_validator_truncates_untrusted_container_logs(tmp_path: Path) -> None:
    validator = DockerPythonValidator(
        tmp_path,
        ValidatorSettings(python_image=PINNED_IMAGE),
        command_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "x" * 250_000, ""),
    )
    logs = validator._logs("container")
    assert len(logs) < 201_000
    assert logs.endswith("[Validator-Logs wegen Größenlimit abgeschnitten]")
