# Docker examples

These examples use the same architecture as the integration suite, but expose
it as a small interactive laboratory:

```text
                          HTTP control
                        +--------------+
                        |              v
+--------+   SSH   +-------------+   +-------+
| runner | ------> | ssh-proxy-a | ->| ssh-a |
|        |         +-------------+   +-------+
|        |   SSH   +-------------+   +-------+
|        | ------> | ssh-proxy-b | ->| ssh-b |
+--------+         +-------------+   +-------+
```

The two targets run real OpenSSH and tmux. The proxies can close active SSH
connections without stopping the target container, which demonstrates why
launcher-managed tmux processes survive transport failures.

## Run the examples

Requirements: Docker with Compose v2 and `ssh-keygen` on the host.

```bash
# Prepare the lab and leave it running for manual CLI exploration.
./examples/docker/prepare.sh

# Colored CLI: dependency startup, status, watch, and shutdown.
./examples/docker/run.sh cli

# ANSI-free asyncio API: events, structured status, and a bounded watch.
./examples/docker/run.sh api

# Typed RemoteConnectionError and explicit Launcher.recover().
./examples/docker/run.sh recovery

# Open a shell in the runner and issue commands manually.
./examples/docker/run.sh shell
```

The script creates an ephemeral SSH key, builds the lab, runs one example, and
removes containers, volumes, and keys when the command exits.

`prepare.sh` creates the same ephemeral key and starts the SSH/proxy services,
but leaves them running. It prints suggested `docker compose run --rm runner ...`
commands, host-side `concert_launcher` commands, and the cleanup commands to
use when you are done experimenting.

After `prepare.sh`, the lab is also reachable from the host through loopback
ports:

| Service | SSH | Control |
| --- | --- | --- |
| `ssh-proxy-a` | `127.0.0.1:2222` | `http://127.0.0.1:8474` |
| `ssh-proxy-b` | `127.0.0.1:2223` | `http://127.0.0.1:8475` |

Source the generated environment file before using the host-facing launcher
configuration:

```bash
source examples/docker/.state/host-env
concert_launcher status
concert_launcher run heartbeat_a
concert_launcher watch heartbeat_a
concert_launcher kill --all
```

## Configuration schema

[`launcher.yaml`](launcher.yaml) is executable documentation. Its graph is:

```text
heartbeat_a on ssh-a       heartbeat_b on ssh-b

http_probe on ssh-b
    `-- depends on web on ssh-a
```

### `context`

| Field | Purpose |
| --- | --- |
| `session` | Default tmux session for persistent processes. Required. |
| `params` | Default `{name}` substitutions shared by commands and checks. |

### Process fields

| Field | Default | Purpose |
| --- | --- | --- |
| `cmd` | required | Shell command to execute. |
| `machine` | `local` | Target in `user@host` form, or `local`. |
| `depends` | `[]` | Processes started and made ready before this process. |
| `ready_check` | none | Command polled until it exits successfully. |
| `persistent` | `true` | Run under tmux; `false` runs once and returns success/failure. |
| `session` | `context.session` | Override the tmux session for one process. |
| `docker` | none | Wrap the command in `docker exec` on the selected machine. The demo hosts intentionally do not run Docker. |
| `force_sigquit` | `false` | Skip graceful SIGINT and stop with SIGQUIT. |
| `variants` | `{}` | Named command/parameter choices selected at execution time. |

CLI parameters override `context.params`:

```bash
concert_launcher run http_probe --params probe_message:=from-cli
```

Variant choices can replace parameters or wrap the base command:

```bash
concert_launcher run http_probe --variants verbose
```

Only one choice from each variant group may be selected.

## CLI example

[`cli_demo.sh`](cli_demo.sh) demonstrates:

- automatic dependency startup and readiness checks;
- one-shot versus persistent processes;
- stable process-label colors in `watch`;
- semantic state colors in `status`;
- `run`, `watch`, `status`, and `kill`.

Colors are enabled only when the CLI writes to an interactive terminal.
Redirected output, `NO_COLOR`, and `TERM=dumb` remain ANSI-free.

## Asyncio API example

[`api_demo.py`](api_demo.py) uses the same YAML and shows:

- `Launcher.execute_process()` with parameters, variants, and event callbacks;
- structured `Launcher.status()` results;
- a custom plain-text watch callback;
- deterministic cleanup with `Launcher.kill()` and `Launcher.close()`.

The library API does not add terminal color unless an application explicitly
injects its own reporter.

## Recovery example

[`recovery_demo.py`](recovery_demo.py) starts a heartbeat in tmux, disables the
SSH proxy, catches `RemoteConnectionError`, restores the proxy, and calls
`Launcher.recover()`. The heartbeat process is never stopped during the outage.
