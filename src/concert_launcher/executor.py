from typing import List, Dict
import os
import logging
import time
from fabric import Connection
from concert_launcher import print_utils, config, remote

logger = logging.getLogger(__name__)

connection_map : Dict[str, Connection] = dict()

class ConfigParser:

    def __init__(self, process, cfg) -> None:
        
        self.print = print_utils.ProgressReporter.get_print_fn(process)
        
        self.verbose = config.ConfigOptions.verbose
        
        # parse config
        pfield = cfg[process]
        
        self.machine = pfield.get('machine', None)

        if self.machine == 'local':
            self.machine = None
        
        self.cmd = pfield['cmd']
        
        self.ready_check = pfield.get('ready_check', None)
        
        self.persistent = pfield.get('persistent', True)
        
        self.session = cfg['session']
        
        self.deps = pfield.get('depends', [])

        # connect to remote
        if self.machine is not None and self.machine not in connection_map.keys():
            self.print(f'opening ssh connection to remote {self.machine}')
            self.ssh = Connection(self.machine)
            connection_map[self.machine] = self.ssh 
        elif self.machine is not None:
            self.ssh = connection_map[self.machine]
        else:
            self.ssh = None 


@print_utils.ProgressReporter.count_calls
def execute_process(process, cfg):

    e = ConfigParser(process=process, cfg=cfg)

    for dep in e.deps:
        e.print(f'depends on {dep}')
        execute_process(dep, cfg)

    ssh = e.ssh

    # copy needed files to remote
    remote.putfile(ssh, os.path.dirname(__file__) + "/concert_launcher_wrapper.bash", '/tmp')

    # non-persistent are just one shot commands
    if not e.persistent:
        e.print(f'running command')
        exitcode, stdout, stderr = remote.run_cmd(ssh, e.cmd)
        for l in stdout.split('\n'):
            e.print(f'[stdout] {l}')
        if exitcode != 0:
            e.print(f'failed (exit code {exitcode})')
        else:
            e.print(f'success')
        return
    
    # check already running
    session_exists = remote.tmux_session_alive(ssh, e.session, process)
    
    if session_exists:
        e.print(f'exists')
    else:
        e.print(f'running process')
        remote.tmux_spawn_new_session(ssh, e.session, process, e.cmd)

    
    if e.ready_check is not None:

        e.print('checking for readiness')

        while True:

            logger.info(f'running ready check for process {process}')

            retcode, _, _ = remote.run_cmd(ssh, e.ready_check)

            if retcode == 0:
                logger.info(f'ready check for process {process} returned 0')
                break

            if not remote.tmux_session_alive(ssh, e.session, process):

                raise RuntimeError(f'process {e.session}:{process} no longer exists')


    e.print(f'ready')


@print_utils.ProgressReporter.count_calls
def kill(process, cfg):

    # if process is none, kill all
    if process is None:
        
        pprint = print_utils.ProgressReporter.get_print_fn('all')

        pprint('killing all processes')

        for process, pfield in cfg.items():

            if not isinstance(pfield, dict):
                continue
            
            kill(process, cfg)

        return

    # parse config
    e = ConfigParser(process=process, cfg=cfg)
        
    # look up dependant processes
    for pname, pfield in cfg.items():

        if pname == process:
            continue
        
        try:
            deps = pfield['depends']
        except:
            continue

        if process in deps:
            
            e.print(f'found dependant process {pname}')

            kill(pname, cfg)

    # non-persistent are just one shot commands
    if not e.persistent:
        return 

    # get list of running windows
    lsdict = remote.tmux_ls(e.ssh, e.session)

    if process not in lsdict.keys():
        e.print('not running')
        return

    if lsdict[process]['dead']:
        e.print('already dead')
        return
        
    e.print('killing with SIGINT')

    pid = lsdict[process]['pid']

    # send CTRL+C
    remote.run_cmd(e.ssh, f'tmux send-keys -t {e.session}:{process} C-c C-m Enter',
                   interactive=False,
                   throw_on_failure=True) 
    
    attempts = 0

    # wait for exit, possibly escalate to CTRL+\
    while remote.tmux_session_alive(e.ssh, e.session, process):
        e.print('waiting for exit..')
        time.sleep(1)
        attempts += 1
        if attempts > 5:
            e.print('killing with SIGKILL')
            remote.run_cmd(e.ssh, f'tmux send-keys -t {e.session}:{process} C-\\\ C-m Enter',
                           interactive=False,
                           throw_on_failure=True) 

            
@print_utils.ProgressReporter.count_calls
def status(process, cfg):

    for process, pfield in cfg.items():

        if not isinstance(pfield, dict):
            continue

        e = ConfigParser(process=process, cfg=cfg)

        ssh = e.ssh

        # copy required files to remote
        remote.putfile(ssh, 
                       os.path.dirname(__file__) + "/print_ps_tree.py", 
                       '/tmp/concert_launcher_print_ps_tree.py')

        # get list of running windows
        lsdict = remote.tmux_ls(ssh, e.session)

        try:
            
            # this fails if windows does not exist
            pinfo = lsdict[process]

            if pinfo['dead']:
                e.print('dead')
                continue
            
            # print process tree
            retcode, stdout, _ = remote.run_cmd(ssh,
                           f'python3 /tmp/concert_launcher_print_ps_tree.py {pinfo["pid"]}',
                           interactive=False,
                           throw_on_failure=True)
            
            e.print('process tree: ')
            print('  ', stdout.replace('\n', '\n  '))

        except:
            pass
    