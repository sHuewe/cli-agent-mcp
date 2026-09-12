# Python Validator MCP

The Python Validator executes project code through Docker and is therefore maintained outside the `cli-agent` core. Its security and Docker-host implications can be reviewed independently from the general agent.

The validator accepts only project-relative paths below the fixed workspace. Before Docker is started, the selected project is copied to a temporary staging directory while common credential, environment, key, log and tool-state files are excluded. The original workspace is never mounted into the container.

The Docker image must be referenced by a complete `@sha256:` digest. Docker runs with `--pull never`, a non-root UID/GID, read-only root filesystem, a restricted `/tmp`, dropped capabilities, `no-new-privileges`, process/memory/CPU limits and `--network none` by default. `bridge` is an explicit opt-in and should only be used for a separately assessed trusted scenario.

Validation proves only that dependency installation and process startup succeeded. It is not a functional test.

Example:

```text
cli-agent-python-validator-mcp --project-directory C:\dev\project --python-image registry.internal/python@sha256:<digest>
```
