from typing import Dict
import logging
from . import remote
from fabric import Connection
import os
from .executor import ConfigParser

ssh = None

logger = logging.getLogger(__name__)

num_cols = 3
pane_to_split = 0
num_rows = 1
num_panes = 0

pkg_already_processed = set()

def create_monitoring_session(process: str, cfg: Dict, level=0):

    if process is None:
        for pname, pfield in cfg.items():
            if not isinstance(pfield, dict):
                continue
            create_monitoring_session(pname, cfg, 0)
        return

    e = ConfigParser(process, cfg)

    # process deps
    for dep in e.deps:
        logging.info(f'{process} depends on {dep}')
        create_monitoring_session(dep, cfg, level+1)

    # dont repeat twice
    if process in pkg_already_processed:
        return
        
    pkg_already_processed.add(process)

    # if not persistent, exit
    if not e.persistent:
        return

    # define monitoring command (connect ssh -> wait for session -> attach)
    cmd = f"while ! tmux has-session -t {process}:{process}; do echo waiting for session {process} to exist..; sleep 1; done; unset TMUX; tmux a -t {process}:{process}"
    
    if e.machine is not None:
        cmd = f"ssh {e.machine} -tt '{cmd}'"
    
    # on first time, ssh connection to local pc (tbd: support remote maybe)
    # and session creation
    global num_rows
    global num_panes
    global pane_to_split

    print(f'adding session {process} to monitor')

    tmux_session = f'{e.session}_mon'

    if num_panes == 0:  
    
        # kill and re-create monitor session
        remote.run_cmd(ssh,
                   f'tmux kill-session -t {tmux_session}',
                   interactive=False,
                   throw_on_failure=False)
        
        remote.run_cmd(ssh, 
                       f'tmux new-session -d -s {tmux_session} "{cmd}"',
                       interactive=False,
                       throw_on_failure=True)
        
        num_panes = 1
        
        remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} mouse on",
                interactive=False,
                throw_on_failure=True)   
        
        remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} aggressive-resize on",
                interactive=False,
                throw_on_failure=True)   
        
        remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} remain-on-exit on",
                interactive=False,
                throw_on_failure=True)
        
        print(f'moniting session created (tmux a -t {tmux_session})')
        
        return

    
    # create pane by splitting the window
        
    logging.info(f"level = {level}  num_rows =  {num_rows}  num_cols = {num_cols}  num_panes = {num_panes}  pane_to_split = {pane_to_split}")

    split_type = '-h' if num_rows == 1 else '-v'
        
    remote.run_cmd(ssh,
                   f'tmux split-window {split_type} -t {tmux_session}:0.{pane_to_split} "{cmd}"',
                   interactive=False,
                   throw_on_failure=False)
    
    pane_to_split += num_rows

    num_panes += 1

    if num_panes == num_cols*num_rows:
        pane_to_split = num_rows - 1
        num_rows += 1

    # redraw layout
    layout = 'even-horizontal' if num_rows == 1 else 'tiled'
    remote.run_cmd(ssh,
                   f'tmux select-layout -t {tmux_session}:0 {layout}',
                   interactive=False,
                   throw_on_failure=False)
    
    # return session name
    return tmux_session
    