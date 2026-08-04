from typing import Dict
import logging
import shlex
from . import remote
import asyncio
import os
from .connections import ConnectionManager
from .executor import ConfigParser

ssh = None

logger = logging.getLogger(__name__)

num_cols = 3
pane_to_split = 0
num_rows = 1
num_panes = 0
pane_targets = []

pkg_already_processed = set()

lock = asyncio.Lock()

async def create_monitoring_session(process: str, cfg: Dict, level=0, monitor_session=None):

    default_session = cfg["context"]["session"]
    session_names = {default_session}

    if level == 0:
        pkg_already_processed.clear()

        for pname, pfield in cfg.items():
            if pname == "context" or not isinstance(pfield, dict):
                continue
            session_names.add(pfield.get("session", default_session))

        logging.info('found session names: %s' % session_names)

        for s in session_names:

            global num_cols 
            global pane_to_split 
            global num_rows 
            global num_panes 
            global pane_targets

            num_cols = 3
            pane_to_split = 0
            num_rows = 1
            num_panes = 0
            pane_targets = []

            logging.info('processing session %s' % s)
            await _reset_monitor_session(s + "_mon")

            for pname, pfield in cfg.items():

                if pname == 'context':
                    continue
                
                ps = pfield.get('session', cfg['context']['session'])
                
                if ps != s:
                    continue

                logging.info('processing process %s' % pname)

                await create_monitoring_session(
                    pname,
                    cfg,
                    level=1,
                    monitor_session=s + "_mon",
                )

        return

    e = ConfigParser(process=process, cfg=cfg, level=level)

    await e.connect()

    # do process
    async with lock:
        await _create_monitoring_session_non_reentrant(
            e,
            process,
            level,
            monitor_session or default_session + "_mon",
        )


def _remote_attach_command(session, process):
    target = "{}:{}".format(session, process)
    quoted_target = shlex.quote(target)
    return (
        "while ! tmux has-session -t {target}; do "
        "echo waiting for session {label} to exist..; "
        "sleep 1; "
        "done; "
        "unset TMUX; "
        "tmux attach -t {target}"
    ).format(target=quoted_target, label=shlex.quote(target))


def _ssh_monitor_command(machine, command):
    user, host, port = ConnectionManager._parse_machine(machine)
    args = ["ssh", "-tt"]

    key_path = os.environ.get("CONCERT_LAUNCHER_SSH_KEY")
    known_hosts = os.environ.get("CONCERT_LAUNCHER_KNOWN_HOSTS")
    if key_path:
        args.extend(["-i", key_path, "-o", "IdentitiesOnly=yes"])
    if known_hosts:
        args.extend([
            "-o",
            "UserKnownHostsFile={}".format(known_hosts),
            "-o",
            "StrictHostKeyChecking=yes",
        ])
    if port is not None:
        args.extend(["-p", str(port)])

    args.extend(["{}@{}".format(user, host), command])
    return " ".join(shlex.quote(arg) for arg in args)


def _monitor_command(e, process):
    command = _remote_attach_command(e.session, process)
    if e.machine is not None:
        return _ssh_monitor_command(e.machine, command)
    return command


async def _reset_monitor_session(tmux_session):
    await remote.run_cmd(
        ssh,
        "tmux kill-session -t {}".format(shlex.quote(tmux_session)),
        throw_on_failure=False,
    )


async def _create_monitoring_session_non_reentrant(e: ConfigParser, process: str, level, tmux_session):

    # dont repeat twice
    if process in pkg_already_processed:
        return
        
    pkg_already_processed.add(process)

    # if not persistent, exit
    if not e.persistent:
        return

    # define monitoring command (connect ssh -> wait for session/window -> attach)
    cmd = _monitor_command(e, process)
    
    # on first time, ssh connection to local pc (tbd: support remote maybe)
    # and session creation
    global num_rows
    global num_panes
    global pane_to_split
    global pane_targets

    print(f'adding session {process} to monitor')

    if num_panes == 0:  
    
        ret, _, _ = await remote.run_cmd(ssh,
                        "tmux has-session -t {}".format(shlex.quote(tmux_session)),
                        throw_on_failure=False)
        if ret != 0:
            await remote.run_cmd(
                ssh,
                "tmux new-session -d -s {session} -n {window} {cmd}".format(
                    session=shlex.quote(tmux_session),
                    window=shlex.quote(e.session),
                    cmd=shlex.quote(cmd),
                ),
            )
            
            await remote.run_cmd(ssh, 
                                 "tmux set -t {} status-style bg=magenta".format(
                                     shlex.quote(tmux_session)
                                 ))

        else:
            target = "{}:{}".format(tmux_session, e.session)
            await remote.run_cmd(
                ssh,
                (
                    "tmux kill-window -t {target} || true; "
                    "tmux new-window -d -t {session} -n {window} {cmd}"
                ).format(
                    target=shlex.quote(target),
                    session=shlex.quote(tmux_session),
                    window=shlex.quote(e.session),
                    cmd=shlex.quote(cmd),
                ),
            )
        
        num_panes = 1
        _, pane_id, _ = await remote.run_cmd(
            ssh,
            "tmux display-message -p -t {} '#{{pane_id}}'".format(
                shlex.quote("{}:{}.0".format(tmux_session, e.session))
            ),
        )
        pane_targets = [pane_id.strip()]
        
        await remote.run_cmd(ssh, 
                "tmux set -t {} mouse on".format(shlex.quote(tmux_session)))
        
        
        await remote.run_cmd(ssh, 
                "tmux set -t {} aggressive-resize on".format(
                    shlex.quote(tmux_session)
                ))
        
        await remote.run_cmd(ssh, 
                "tmux set -t {} remain-on-exit on".format(
                    shlex.quote(tmux_session)
                ))
        
        print(f'monitoring session created (tmux a -t {tmux_session})')
        
        return

    
    # create pane by splitting the window
        
    logging.info(f"level = {level}  num_rows =  {num_rows}  num_cols = {num_cols}  num_panes = {num_panes}  pane_to_split = {pane_to_split}")

    split_type = '-h' if num_rows == 1 else '-v'
        
    split_target = pane_targets[pane_to_split]
    _, pane_id, _ = await remote.run_cmd(
        ssh,
        "tmux split-window -P -F '#{{pane_id}}' {split_type} -t {target} {cmd}".format(
            split_type=split_type,
            target=shlex.quote(split_target),
            cmd=shlex.quote(cmd),
        ),
        interactive=False,
    )
    pane_targets.append(pane_id.strip())
    
    pane_to_split += num_rows

    num_panes += 1

    if num_panes == num_cols*num_rows:
        pane_to_split = num_rows - 1
        num_rows += 1

    # redraw layout
    layout = 'even-horizontal' if num_rows == 1 else 'tiled'
    await remote.run_cmd(ssh,
                   "tmux select-layout -t {} {}".format(
                       shlex.quote("{}:{}".format(tmux_session, e.session)),
                       shlex.quote(layout),
                   ),
                   interactive=False,
                   throw_on_failure=False)
    
    # return session name
    return tmux_session
    
