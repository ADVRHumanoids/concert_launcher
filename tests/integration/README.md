# Docker SSH integration tests

These tests exercise Concert Launcher against real OpenSSH and tmux processes.
They are intentionally separate from the mocked unit suite.

## Requirements

- Docker Engine
- Docker Compose v2
- `ssh-keygen` on the host

## Run

From the repository root:

```bash
./tests/integration/run.sh
```

Pass normal pytest arguments after the script name:

```bash
./tests/integration/run.sh pytest -m docker tests/integration/test_remote_execution.py -v
```

The script generates an ephemeral Ed25519 client key, builds two SSH hosts and a
pytest runner on an isolated Compose network, executes the tests, and removes
all containers, volumes, and key material afterward.

The first implementation slice covers:

- real AsyncSSH authentication
- SCP deployment of launcher resources
- one-shot remote commands
- persistent tmux execution
- status inspection
- live output streaming
- remote exit-code recovery
- graceful stop behavior

Planned follow-up coverage includes cross-host dependencies and deterministic
network interruption/recovery through a proxy service.
