# Concert Launcher

Concert Launcher starts and supervises dependency graphs of processes locally,
over SSH, or inside Docker containers. Processes run in `tmux`, so they remain
alive after the launching shell or SSH connection exits.

## Highlights

- YAML process graphs with dependencies, parameters, and variants
- Local, SSH, and Docker execution
- Start, stop, status, process-tree, and output-watch commands
- Readable terminal progress and aligned status tables
- A reusable asyncio API with typed, recoverable SSH errors

## Installation

```bash
pip install -e .
```

Both local and remote target machines need `tmux`. SSH authentication is handled
by AsyncSSH and normally uses the same keys and agent as OpenSSH.

## Configuration

```yaml
context:
  session: robot
  params:
    robot_name: centauro

robot_state:
  cmd: robot_state_publisher --robot {robot_name}
  machine: operator@robot-pc
  ready_check: pgrep -f robot_state_publisher

controller:
  cmd: controller --mode position
  machine: operator@robot-pc
  depends: [robot_state]
  variants:
    debug:
      cmd: "{cmd} --verbose"
    mode:
      - position:
          params: {control_mode: position}
      - torque:
          params: {control_mode: torque}
```

`machine` can be omitted or set to `local`. Remote machines use the
`user@host` form.

## CLI

```bash
concert_launcher run controller
concert_launcher run controller --variants debug torque
concert_launcher run controller --params robot_name:=kyon
concert_launcher run controller --ssh-retries 2
concert_launcher status
concert_launcher status --watch
concert_launcher watch controller
concert_launcher kill controller
concert_launcher kill --all
```

Status output is grouped into stable columns and explicitly marks unavailable
hosts instead of silently omitting them.

## Asyncio API

```python
import yaml
from concert_launcher import Launcher

with open("launcher.yaml") as stream:
    config = yaml.safe_load(stream)

launcher = Launcher(config)

try:
    await launcher.execute_process(
        "controller",
        variants=["debug"],
        params={"robot_name": "kyon"},
    )
finally:
    await launcher.close()
```

The class API does not terminate the Python interpreter. For example,
`wait_process()` returns the remote process exit status instead of calling
`exit()`.

## Recovering from SSH failures

AsyncSSH and socket transport errors are normalized into
`RemoteConnectionError`. The exception identifies the affected machine, keeps
the original exception in `cause`, and has `retryable = True`.

### Recover explicitly

```python
from concert_launcher import RemoteConnectionError

try:
    await launcher.execute_process("controller")
except RemoteConnectionError as error:
    # Drops the stale cached connection and verifies a fresh connection.
    await launcher.recover(error)
    await launcher.execute_process("controller")
```

### Retry automatically

```python
await launcher.execute_with_recovery(
    "controller",
    retries=3,
    retry_delay=2.0,
)
```

A failed SSH connection is never cached, and a closed cached connection is
replaced on the next operation. Concert Launcher never treats a failed remote
connection as local execution.

For status dashboards which should continue when one host is offline:

```python
status = await launcher.status(
    print_to_stdout=False,
    raise_on_unavailable=False,
)
```

Unavailable processes are returned with `state == "UNAVAILABLE"` and an
`error` field. The default library behavior is to raise
`RemoteConnectionError`, making recovery explicit.

## Event callback

```python
async def on_event(process, message):
    print(process, message)

await launcher.execute_process("controller", notify_event=on_event)
```

The callback receives the process name and a lifecycle message. This signature
is retained for compatibility with the existing function API.

## Backward compatibility

Existing imports continue to work:

```python
from concert_launcher import executor

await executor.execute_process("controller", config)
await executor.status(None, config)
```

New integrations should prefer `Launcher`, which owns connection recovery and
lifetime explicitly.
