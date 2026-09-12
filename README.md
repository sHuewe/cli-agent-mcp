# cli-agent-mcp

Optional MCP servers for [`cli-agent`](https://github.com/sHuewe/cli-agent).

This repository contains MCP servers whose capabilities require additional host privileges or execution surfaces that are not needed by the core agent. Keeping them separate allows `cli-agent` to stay focused on the generic agent/MCP integration while these optional tools can be reviewed and approved independently.

Currently included:

- **Docker Compose MCP**: inspect a Compose project, read service status/logs and optionally start, stop or restart services.
- **Python Validator MCP**: copy a Python project into a sanitized staging directory and validate build/start behavior in a short-lived hardened Docker container.

## Security boundary

Both servers interact with Docker or host-side process execution. Access to the Docker daemon is a privileged host boundary and must be assessed separately from the `cli-agent` core. Installing this package does not enable either MCP automatically; each server must be configured explicitly in the agent.

User-provided `stdio` MCP servers are treated as untrusted by `cli-agent`. When these servers are configured there, `allow_untrusted_stdio = true` is required and tool calls remain subject to the agent's approval policy.

## Installation

```powershell
py -m pipx install .
```

For development:

```powershell
python -m pip install -e ".[dev]"
pytest
```

The package installs two commands:

```text
cli-agent-compose-mcp
cli-agent-python-validator-mcp
```

## Docker Compose MCP

Example `cli-agent` configuration:

```toml
[[mcp_servers]]
name = "compose"
transport = "stdio"
command = "cli-agent-compose-mcp"
args = ["--project-directory", "{workspace_directory}"]

[mcp_servers.config]
allow_untrusted_stdio = true
```

Service-changing tools are disabled by default. To expose them, add `--allow-modify-services` to `args`. For a Docker CLI running through WSL, add `--wsl`.

See [docs/compose.md](docs/compose.md) for details.

## Python Validator MCP

The validator requires an immutable Docker image reference by SHA-256 digest and uses `--network none` by default:

```toml
[[mcp_servers]]
name = "python-validator"
transport = "stdio"
command = "cli-agent-python-validator-mcp"
args = [
    "--project-directory", "{workspace_directory}",
    "--python-image", "registry.internal/python@sha256:<64-hex-characters>",
    "--network-mode", "none",
]

[mcp_servers.config]
allow_untrusted_stdio = true
```

The original workspace is never mounted directly into the validation container. A sanitized temporary copy is mounted read-only. The container runs without network access by default, as a non-root user, with a read-only root filesystem, dropped capabilities and `no-new-privileges`.

See [docs/python-validator.md](docs/python-validator.md) for details.
