import logging
import shutil
from . import config
import asyncssh, asyncio

# logger
logger = logging.getLogger(__name__)

async def putfile(remote: asyncssh.SSHClientConnection, 
                  local_path: str, 
                  remote_path: str):
    
    if remote is None:
        shutil.copy(local_path, remote_path)
    else:
        await run_cmd(None, f'scp {local_path} {remote._username}@{remote._host}:{remote_path}', 
                      interactive=False, throw_on_failure=True)


async def run_cmd(remote: asyncssh.SSHClientConnection, 
                  cmd: str, 
                  timeout=None, 
                  interactive=False, 
                  throw_on_failure=True):
    
    verbose = config.ConfigOptions.verbose

    if interactive:
        cmd_real = f"bash -ic '{cmd}'"
    else:
        cmd_real = cmd
    
    logger.info(f'running {cmd_real}')

    if remote is None:
        proc = await asyncio.create_subprocess_shell(cmd_real, 
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout, stderr = stdout.decode(), stderr.decode()
        retcode = proc.returncode
    else:
        res = await remote.run(cmd_real, check=False, timeout=timeout)
        retcode = res.returncode
        stdout = res.stdout
        stderr = res.stderr

    logger.debug(f'{cmd} exitcode: {retcode}')

    logger.debug(f'{cmd} stdout: {stdout}')

    logger.debug(f'{cmd} stderr: {stderr}')

    if throw_on_failure and retcode != 0:
        raise RuntimeError(f'command {cmd} returned {retcode}')

    return retcode, stdout.strip(), stderr.strip()


async def watch_process(remote: asyncssh.SSHClientConnection, 
                        cmd: str, 
                        stdout_coro,
                        interactive=False, 
                        throw_on_failure=True):
    
    if remote is None: 
        proc = await asyncio.create_subprocess_shell(cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE)
        decode = True
    else:
        proc = await remote.create_process(cmd)
        decode = False
    
    while True:
        l = await proc.stdout.readline()
        if decode:
            l = l.decode()
        if len(l) == 0:
            return
        await stdout_coro(l)


async def tmux_ls(remote: asyncssh.SSHClientConnection, session: str):
    
    list_w_cmd = "tmux list-w -t %s -F '#{session_name} #{window_name} #{pane_pid} #{pane_dead} #{pane_dead_status}'" % session
    
    retcode, stdout, _ = await run_cmd(remote, list_w_cmd, throw_on_failure=False)
    
    if retcode == 1:
        return {}
    
    if retcode != 0:
        raise RuntimeError(f'tmux list-w returned unexpected exit code {retcode}')
    
    logger.info(f'tmux ls got stdout: {stdout}')
    
    ret = dict()

    for l in stdout.split('\n'):
        
        tokens = l.strip().split(' ')

        if len(tokens) == 4:
            tokens.append(0)
        
        sname, wname, pid, dead, dead_status = tokens
        
        if sname != session:
            continue
        ret[wname] = {
            'pid': int(pid),
            'dead': int(dead) == 1,
            'exitstatus': int(dead_status),
        }

    logger.info(f'tmux ls returns: {ret}')

    return ret



async def tmux_has_session(remote: asyncssh.SSHClientConnection, session: str, window: str):

    retcode, _, _ = await run_cmd(remote, f'tmux has-session -t {session}:{window}', throw_on_failure=False)

    if retcode == 0:
        return True
    elif retcode == 1:
        return False
    else:
        raise RuntimeError(f'tmux_has_session: tmux returned unexpected code {retcode}')


async def tmux_session_alive(remote: asyncssh.SSHClientConnection, session: str, window: str):

    if not await tmux_has_session(remote, session, window):

        return False

    lsdict = await tmux_ls(remote, session)

    return window in lsdict.keys() and not lsdict[window]['dead']



tmux_spawn_new_session_lock = asyncio.Lock()

async def tmux_spawn_new_session(remote: asyncssh.SSHClientConnection, session: str, window: str, cmd: str):

    async with tmux_spawn_new_session_lock:
        logger.debug(f'>>>>>>>>>>> BEGIN _tmux_spawn_new_session {session}:{window}')
        ret = await _tmux_spawn_new_session(remote, session, window, cmd)
        logger.debug(f'<<<<<<<<<<< END   _tmux_spawn_new_session {session}:{window}')
        return ret


async def _tmux_spawn_new_session(remote: asyncssh.SSHClientConnection, session: str, window: str, cmd: str):

    lsdict = await tmux_ls(remote, session)

    if len(lsdict) == 0:
        
        cmds = [
            f"tmux new-session -d -s {session} -n {window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'",
            f"tmux new-session -d -t {session} -s {window}",
            f"tmux set -t {session} aggressive-resize on",
            f"tmux set -t {session} mouse on",
            f"tmux set -t {session} remain-on-exit on",
            f"tmux set -t {session} history-limit 10000",
            f"tmux set -t {window} mouse on",
            f"tmux set -t {window} remain-on-exit on",
            f"tmux set -t {window} history-limit 10000",
        ]
        
        cmd_union = ' && '.join(cmds)

        await run_cmd(remote, cmd_union)
        
    elif window not in lsdict.keys():
        
        cmds = [
            f"tmux new-session -d -t {session} -s {window}",
            f"tmux set -t {window} mouse on",
            f"tmux set -t {window} remain-on-exit on",
            f"tmux set -t {window} history-limit 10000",
            f"tmux new-window -d -a -t {window} -n {window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'",
            f"tmux set -t {window} aggressive-resize on",
        ]

        cmd_union = ' && '.join(cmds)

        await run_cmd(remote, cmd_union)
        
    elif lsdict[window]['dead']:

        await run_cmd(remote, 
                f"tmux respawn-window -t {session}:{window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'") 

    else:

        raise RuntimeError(f'window {window} exists and is not dead')

    cmds = [
        f"tmux set -t {session}:{window} remain-on-exit on",
        f"tmux set -t {session}:{window} history-limit 10000",
    ]
        
    cmd_union = ' && '.join(cmds)

    await run_cmd(remote, cmd_union)
    
