# Concert Launcher

## Overview

The Concert Launcher serves as the core process management system for robotics software stacks, providing:

- **Multi-environment execution**: Run processes locally, on remote machines via SSH, or inside Docker containers
- **Process management**: Start, stop, monitor, and check the status of processes
- **Variants and configurations**: Define different execution configurations for the same process
- **Parametrization**: Customize process execution with context parameters
- **Robust execution**: Uses `tmux` for reliable background process management
- **Real-time monitoring**: Stream process output and monitor process status

## Core Components

### concert_launcher/src/concert_launcher/executor.py

The `executor.py` module is the heart of the Concert Launcher system. It implements the `Executor` class, which contains the following core functionality:

1. **Configuration Management**:
   - Parses the `launcher_config.yaml` file, resolving aliases and handling default parameters
   - Understands variant configurations and applies them to process definitions
   - Constructs final command strings with parameter substitution and variant modifications

2. **Environment Handling**:
   - Supports local execution, remote execution via SSH, and containerized execution in Docker
   - Handles necessary command wrapping for Docker execution (e.g., `docker exec -it <container> bash -ic "<cmd>"`)
   - Provides a consistent process management interface regardless of execution environment

3. **SSH Integration**:
   - Uses the `asyncssh` library to establish asynchronous SSH connections to remote machines
   - Manages SSH sessions effectively to avoid connection leaks or timeouts
   - Supports various authentication methods (password, key-based)

4. **tmux Integration**:
   - Launches processes within tmux sessions on target machines for persistence
   - Creates dedicated tmux windows for each process with appropriate naming
   - Uses tmux commands to start, monitor, and terminate processes reliably
   - Enables processes to continue running even if the SSH connection drops

5. **Process Management**:
   - **Start**: Launches processes with appropriate environment setup and variant configurations
   - **Stop/Kill**: Sends signals (SIGINT for graceful, SIGKILL for forced) to processes
   - **Status**: Checks if processes are running, ready, or stopped
   - **Ready Check**: Periodically executes custom commands to verify if a process is fully operational
   - **Process Tree**: Retrieves hierarchical process information for debugging

6. **Output Streaming**:
   - Provides asynchronous streaming of process stdout/stderr
   - Uses efficient techniques (like `tail -f`) to monitor process output
   - Supports filtering and formatting of process output

7. **Event Notification**:
   - Implements a callback mechanism for notifying callers about process events
   - Generates detailed status updates during process lifecycle (starting, checking readiness, ready, error)

### Asynchronous Implementation

The Executor is implemented using Python's `asyncio` framework, allowing for:

- Non-blocking I/O operations (especially important for SSH and process monitoring)
- Concurrent management of multiple processes
- Efficient resource utilization
- Responsive status checking and event notification

## Configuration Format

The Concert Launcher uses a flexible YAML configuration format. Here's an example of it, that can be find in Kyon-Config repo [Kyon-Config](https://github.com/ADVRHumanoids/kyon_config):

```yaml
context:
  session: my_session       # Default tmux session name for process grouping
  params:                   # Global parameters accessible via {param_name} substitution
    hw_type: default_type   # Example parameter used in commands
  .defines:                 # YAML Anchors for reusable aliases
    - &local localhost      # Define local machine alias
    - &remote user@host     # Define remote SSH target
    - &docker_xeno container_name  # Define Docker container name

# Process Definitions (each top-level key except 'context' defines a process)
process_name:
  cmd: executable --param {hw_type}  # Command with parameter substitution
  machine: *remote          # WHERE: Run on machine referenced by 'remote' alias (via SSH)
  docker: *docker_xeno      # HOW: Run inside Docker container referenced by 'docker_xeno'
  ready_check: test_command # Command to verify process is ready (exit code 0 = ready)
  variants:                 # Alternative configurations
    simple_flag:            # Simple flag variant (adds to command)
      cmd: "{cmd} --verbose"  # Appends to base command using {cmd} as placeholder
    option_group:           # Group of mutually exclusive options (like radio buttons)
      - option1:            # Option name
          params:           # Option-specific parameters
            hw_type: type1  # Overrides the global hw_type for this variant
      - option2:
          params:
            hw_type: type2
```

### Process Execution Flow

When executing a process (`execute_process()`), the Executor:

1. Retrieves the process definition from the configuration
2. Applies selected variants to determine the final command and parameters
3. Establishes connection to the target machine (local or via SSH)
4. Constructs the appropriate execution command based on environment:
   - For local: executes directly
   - For SSH: wraps command appropriately
   - For Docker: wraps with `docker exec` command
5. Uses tmux to launch the process in a dedicated window:
   ```bash
   tmux new-window -d -n process_name -t session: 'command'
   ```
6. Captures process output to a temporary file for monitoring
7. If a `ready_check` is defined, periodically executes it until success
8. Updates process status and notifies via events/callbacks

### Process Monitoring and Status

The Executor provides comprehensive monitoring capabilities:

- **Status Checking**: Uses tmux commands to check if a process is still running:
  ```bash
  tmux list-windows -t session: -F '#{window_name} #{pane_pid}'
  ```

- **Process Tree**: Retrieves the full process tree for debugging:
  ```bash
  pstree -p $(tmux list-panes -t session:window -F '#{pane_pid}')
  ```

- **Output Streaming**: Watches process output in real-time:
  ```bash
  tail -f /tmp/process_output.log
  ```

## API Reference

```python
from concert_launcher.executor import Executor

# Initialize with configuration file
executor = Executor("launcher_config.yaml")

# Execute a process with variants
await executor.execute_process(
    "process_name",           # Process name as defined in config
    variants=["option1"],     # Selected variants
    on_event=callback_func    # Optional callback for status events
)

# Kill a process
await executor.kill(
    "process_name",           # Process to terminate
    graceful=True,            # True for SIGINT, False for SIGKILL
    on_event=callback_func    # Optional event callback
)

# Check process status
status = await executor.status("process_name")
# Returns: 0 (Stopped), 1 (Running), 2 (Ready), -1 (Error)

# Get process tree
pstree = await executor.pstree("process_name")
# Returns: String representation of process hierarchy

# Stream process output
async for line in executor.watch("process_name"):
    print(line)  # Process each line of output

# Check all processes
all_status = await executor.status()
# Returns: Dictionary mapping process names to status codes
```

## Event Notification System

The Executor implements an event notification system through callbacks. When provided with an `on_event` function, it sends detailed status events during process lifecycle:

```python
async def on_launcher_event(event_type, process_name, message, level=0):
    """
    Callback for launcher events.
    
    Args:
        event_type: Type of event (start, ready_check, ready, error, kill)
        process_name: Name of the process
        message: Detailed message about the event
        level: Severity level (0=info, 1=warning, 2=error)
    """
    print(f"[{process_name}] {event_type}: {message}")

# Use with execute_process
await executor.execute_process("my_process", on_event=on_launcher_event)
```

Typical events include:
- "Connecting via SSH..."
- "Starting process..."
- "Checking readiness..."
- "Process ready"
- "Error: Ready check failed"
- "Process killed"

## Integration with Other Systems

The Concert Launcher is designed to be used as a library by other applications. Common integration patterns include:

### Web Server Integration

```python
# Example integration with aiohttp web server
from aiohttp import web
from concert_launcher.executor import Executor

class LauncherServer:
    def __init__(self, config_path):
        self.executor = Executor(config_path)
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        self.app.router.add_get('/process/list', self.handle_process_list)
        self.app.router.add_put('/process/{name}/command/{command}', self.handle_command)
        
    async def handle_process_list(self, request):
        processes = self.executor.get_processes()
        status = await self.executor.status()
        return web.json_response({
            'processes': processes,
            'status': status
        })
        
    async def handle_command(self, request):
        name = request.match_info['name']
        command = request.match_info['command']
        
        if command == 'start':
            data = await request.json()
            variants = data.get('variants', [])
            await self.executor.execute_process(name, variants)
        elif command == 'stop':
            await self.executor.kill(name, graceful=True)
            
        return web.json_response({'success': True})
```

## Installation

Tailored to @alaurenzi 's laptop machine setup !

```bash
pip install -e .
cd config/example_alaurenzi  # a folder containing launcher.yaml
concert_launcher run cartesio  # run cartesio and its dependencies
concert_launcher mon  # spawn tmux monitoring session on local machine
concert_launcher status  # print process tree
concert_launcher kill [proc_name]  # kill proc_name (or all)
```
