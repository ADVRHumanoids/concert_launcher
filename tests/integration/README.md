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

The script generates an ephemeral Ed25519 client key, builds two SSH hosts,
two controllable TCP proxies, and a pytest runner on an isolated Compose
network. It executes the tests and removes all containers, volumes, and key
material afterward.

The integration suite covers:

- real AsyncSSH authentication and SCP resource deployment
- one-shot remote commands and persistent tmux execution
- status inspection, live output streaming, and remote exit-code recovery
- graceful SIGINT delivery to a foreground application
- dependency ordering across separate SSH hosts
- deterministic SSH interruption without stopping the remote host
- manual reconnection while tmux processes continue running
- output-watch reconnection with line-position recovery

The proxies expose a private control endpoint only on the Compose network.
Disabling one closes active SSH sockets and rejects new connections while the
underlying OpenSSH container and its tmux sessions remain untouched.
