from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .python_validator import DockerPythonValidator
from .python_validator_types import ValidatorSettings


def create_server(validator: DockerPythonValidator) -> FastMCP:
    mcp = FastMCP(
        "Python Docker Validator",
        instructions=(
            "Use validate_python_project after changing Python code when build/start validation is relevant. "
            "Treat success only as evidence that dependencies installed and the process started; it is not a functional test."
        ),
    )

    @mcp.tool()
    def validate_python_project(
        project_path: str,
        entrypoint: str,
        entrypoint_type: Literal["file", "module"] = "file",
        arguments: list[str] | None = None,
        expect_long_running: bool = True,
    ) -> dict[str, Any]:
        """Install and start a Python project in a temporary hardened Docker container."""
        return validator.validate(
            project_path,
            entrypoint,
            entrypoint_type=entrypoint_type,
            arguments=arguments,
            expect_long_running=expect_long_running,
        )

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP server for isolated Python build/start validation")
    parser.add_argument("--project-directory", required=True, type=Path)
    parser.add_argument("--python-image", required=True, help="Immutable Python image reference with @sha256 digest")
    parser.add_argument("--network-mode", choices=("none", "bridge"), default="none")
    parser.add_argument("--setup-timeout", type=int, default=180)
    parser.add_argument("--startup-grace", type=float, default=3.0)
    parser.add_argument("--memory-limit", default="2g")
    parser.add_argument("--cpu-limit", default="2.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = ValidatorSettings(
        python_image=args.python_image,
        network_mode=args.network_mode,
        setup_timeout_seconds=args.setup_timeout,
        startup_grace_seconds=args.startup_grace,
        memory_limit=args.memory_limit,
        cpu_limit=args.cpu_limit,
    )
    create_server(DockerPythonValidator(args.project_directory, settings)).run(transport="stdio")


if __name__ == "__main__":
    main()
