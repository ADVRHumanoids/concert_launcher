from typing import Dict
import logging
from . import remote
import asyncssh, asyncio
import os
from .executor import ConfigParser

ssh = None

logger = logging.getLogger(__name__)

num_cols = 3
pane_to_split = 0
num_rows = 1
num_panes = 0

pkg_already_processed = set()

lock = asyncio.Lock()

async def create_monitoring_session(process: str, cfg: Dict, level=0):

    session_names = set()

    if level == 0:
        
        for pname, pfield in cfg.items():
            if 'session' in pfield.keys():
                session_names.add(pfield['session'])

        logging.info('found session names: %s' % session_names)

        for s in session_names:

            global num_cols 
            global pane_to_split 
            global num_rows 
            global num_panes 

            num_cols = 3
            pane_to_split = 0
            num_rows = 1
            num_panes = 0

            logging.info('processing session %s' % s)

            for pname, pfield in cfg.items():

                if pname == 'context':
                    continue
                
                ps = pfield.get('session', cfg['context']['session'])
                
                if ps != s:
                    continue

                logging.info('processing process %s' % pname)

                await create_monitoring_session(pname, cfg, level=1)

        return

    e = ConfigParser(process=process, cfg=cfg, level=level)

    await e.connect()

    # do process
    async with lock:
        await _create_monitoring_session_non_reentrant(e, process, level, cfg['context']['session'] + '_mon')


async def _create_monitoring_session_non_reentrant(e: ConfigParser, process: str, level, tmux_session):

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

    if num_panes == 0:  
    
        ret, _, _ = await remote.run_cmd(ssh,
                        f'tmux has-session -t {tmux_session}',
                        throw_on_failure=False)
        if ret != 0:
            # kill and re-create monitor session
            await remote.run_cmd(ssh, 
                        f'tmux kill-session -t {tmux_session} || tmux new-session -d -s {tmux_session} -n {e.session} "{cmd}"')
            
            await remote.run_cmd(ssh, 
                                 f'tmux set -t {tmux_session} status-style bg=magenta')

        else:
            await remote.run_cmd(ssh, 
                        f'tmux kill-window -t {tmux_session}:{e.session}; tmux new-window -d -t {tmux_session} -n {e.session} "{cmd}"',
                        throw_on_failure=False)
        
        num_panes = 1
        
        await remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} mouse on")   
        
        
        await remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} aggressive-resize on")   
        
        await remote.run_cmd(ssh, 
                f"tmux set -t {tmux_session} remain-on-exit on")
        
        print(f'moniting session created (tmux a -t {tmux_session})')
        
        return

    
    # create pane by splitting the window
        
    logging.info(f"level = {level}  num_rows =  {num_rows}  num_cols = {num_cols}  num_panes = {num_panes}  pane_to_split = {pane_to_split}")

    split_type = '-h' if num_rows == 1 else '-v'
        
    await remote.run_cmd(ssh,
                   f'tmux split-window {split_type} -t {tmux_session}:{e.session}.{pane_to_split} "{cmd}"',
                   interactive=False,
                   throw_on_failure=False)
    
    pane_to_split += num_rows

    num_panes += 1

    if num_panes == num_cols*num_rows:
        pane_to_split = num_rows - 1
        num_rows += 1

    # redraw layout
    layout = 'even-horizontal' if num_rows == 1 else 'tiled'
    await remote.run_cmd(ssh,
                   f'tmux select-layout -t {tmux_session}:{e.session} {layout}',
                   interactive=False,
                   throw_on_failure=False)
    
    # return session name
    return tmux_session
    