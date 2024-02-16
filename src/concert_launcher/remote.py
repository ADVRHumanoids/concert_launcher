from fabric import Connection
from invoke.exceptions import CommandTimedOut
import invoke
import logging
import shutil
from . import config

# logger
logger = logging.getLogger(__name__)

def putfile(remote: Connection, local_path, remote_path):
    
    if remote is None:
        shutil.copy(local_path, remote_path)
    else:
        remote.put(local_path, remote_path)


def run_cmd(remote: Connection, cmd: str, timeout=None, interactive=True, throw_on_failure=False):
    
    verbose = config.ConfigOptions.verbose

    if interactive:
        cmd_real = f"bash -ic '{cmd}'"
    else:
        cmd_real = cmd
    
    logger.info(f'running {cmd_real}')

    if remote is None:
        remote = invoke
        pty = True
    else:
        pty = False

    res = remote.run(cmd_real, warn=True, hide=True, echo=verbose, timeout=timeout, pty=pty)
    exitcode = res.exited
    stdout = res.stdout
    stderr = res.stderr

    logger.info(f'{cmd} exitcode: {exitcode}')

    logger.info(f'{cmd} stdout: {stdout}')

    logger.info(f'{cmd} stderr: {stderr}')

    if throw_on_failure and exitcode != 0:
        raise RuntimeError(f'command {cmd} returned {exitcode}')

    return exitcode, stdout.strip(), stderr.strip()


def tmux_ls(remote: Connection, session: str):
    
    retcode, stdout, _ = run_cmd(remote, 
                                 "tmux list-w -t %s -F '#{session_name} #{window_name} #{pane_pid} #{pane_dead}'" % session,
                                 interactive=False,
                                 throw_on_failure=False)
    
    if retcode == 1:
        return {}
    
    if retcode != 0:
        raise RuntimeError(f'tmux list-w returned unexpected exit code {retcode}')
    
    logger.info(f'tmux ls got stdout: {stdout}')
    
    ret = dict()

    for l in stdout.split('\n'):
        sname, wname, pid, dead = l.split(' ')
        if sname != session:
            continue
        ret[wname] = {
            'pid': int(pid),
            'dead': int(dead) == 1
        }

    logger.info(f'tmux ls returns: {ret}')

    return ret



def tmux_has_session(remote: Connection, session: str, window: str):

    retcode, _, _ = run_cmd(remote, f'tmux has-session -t {session}:{window}', interactive=False)

    if retcode == 0:
        return True
    elif retcode == 1:
        return False
    else:
        raise RuntimeError(f'tmux_has_session: tmux returned unexpected code {retcode}')


def tmux_session_alive(remote: Connection, session: str, window: str):

    if not tmux_has_session(remote, session, window):

        return False

    lsdict = tmux_ls(remote, session)

    return window in lsdict.keys() and not lsdict[window]['dead']



def tmux_spawn_new_session(remote: Connection, session: str, window: str, cmd: str):

    lsdict = tmux_ls(remote, session)

    if len(lsdict) == 0:

        run_cmd(remote, 
                f"tmux new-session -d -s {session} -n {window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'",
                interactive=False,
                throw_on_failure=True)
        
        run_cmd(remote, 
                f"tmux new-session -d -t {session} -s {window}",
                interactive=False,
                throw_on_failure=True)
        
        run_cmd(remote, 
                f"tmux set -t {window}:{window} status off",
                interactive=False,
                throw_on_failure=True)  

        run_cmd(remote, 
                f"tmux set -t {session} mouse on",
                interactive=False,
                throw_on_failure=True)   
        
        run_cmd(remote, 
                f"tmux set -t {session} remain-on-exit on",
                interactive=False,
                throw_on_failure=True)
    
        run_cmd(remote, 
                f"tmux set -t {session} history-limit 10000",
                interactive=False,
                throw_on_failure=True)
        
    elif window not in lsdict.keys():

        run_cmd(remote, 
                f"tmux new-session -d -t {session} -s {window}",
                interactive=False,
                throw_on_failure=True)
        
        run_cmd(remote, 
                f"tmux set -t {window} status off",
                interactive=False,
                throw_on_failure=True)   
        
        run_cmd(remote, 
                f"tmux set -t {window} mouse on",
                interactive=False,
                throw_on_failure=True)   
        
        run_cmd(remote, 
                f"tmux set -t {window} remain-on-exit on",
                interactive=False,
                throw_on_failure=True)
    
        run_cmd(remote, 
                f"tmux set -t {window} history-limit 10000",
                interactive=False,
                throw_on_failure=True)

        run_cmd(remote, 
                f"tmux new-window -d -t {window} -n {window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'",
                interactive=False,
                throw_on_failure=True)
        
    elif lsdict[window]['dead']:

        run_cmd(remote, 
                f"tmux respawn-window -t {session}:{window} /tmp/concert_launcher_wrapper.bash {window} '{cmd}'",
                interactive=False,
                throw_on_failure=True) 

    else:

        raise RuntimeError(f'window {window} exists and is not dead')

        
    run_cmd(remote, 
                f"tmux set -t {session}:{window} remain-on-exit on",
                interactive=False,
                throw_on_failure=True)
    
    run_cmd(remote, 
                f"tmux set -t {session}:{window} history-limit 10000",
                interactive=False,
                throw_on_failure=True)
    
