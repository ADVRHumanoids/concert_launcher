from typing import List, Dict
import os
import logging
import time
from fabric import Connection
from concert_launcher import print_utils, config, remote

logger = logging.getLogger(__name__)

connection_map : Dict[str, Connection] = dict()

@print_utils.ProgressReporter.count_calls
def execute_process(process, cfg):

    pprint = print_utils.ProgressReporter.get_print_fn(process)
    verbose = config.ConfigOptions.verbose
    
    pfield = cfg[process]
    machine = pfield.get('machine', None)
    if machine == 'local':
        machine = None
    cmd = pfield['cmd']
    ready_check = pfield.get('ready_check', None)
    persistent = pfield.get('persistent', True)
    session = cfg['session']
    
    # run dependencies
    deps = pfield.get('depends', [])
    for dep in deps:
        pprint(f'depends on {dep}')
        execute_process(dep, cfg)

    # connect to remote
    if machine is not None and machine not in connection_map.keys():
        pprint(f'opening ssh connection to remote {machine}')
        ssh = Connection(machine)
        connection_map[machine] = ssh 
    elif machine is not None:
        ssh = connection_map[machine]
    else:
        ssh = None 

    # copy needed files to remote
    remote.putfile(ssh, os.path.dirname(__file__) + "/concert_launcher_wrapper.bash", '/tmp')

    # non-persistent are just one shot commands
    if not persistent:
        pprint(f'running command')
        exitcode, stdout, stderr = remote.run_cmd(ssh, cmd)
        for l in stdout.split('\n'):
            pprint(f'[stdout] {l}')
        if exitcode != 0:
            pprint(f'failed (exit code {exitcode})')
        else:
            pprint(f'success')
        return
    
    # check already running
    session_exists = remote.tmux_session_alive(ssh, session, process)
    
    if session_exists:
        pprint(f'exists')
    else:
        pprint(f'running process')
        remote.tmux_spawn_new_session(ssh, session, process, cmd)

    
    if ready_check is not None:

        pprint('checking for readiness')

        while True:

            logger.info(f'running ready check for process {process}')

            retcode, _, _ = remote.run_cmd(ssh, ready_check)

            if retcode == 0:
                logger.info(f'ready check for process {process} returned 0')
                break

            if not remote.tmux_session_alive(ssh, session, process):

                raise RuntimeError(f'process {session}:{process} no longer exists')


    pprint(f'ready')


@print_utils.ProgressReporter.count_calls
def kill(process, cfg):


    if process is None:
        
        pprint = print_utils.ProgressReporter.get_print_fn('all')

        pprint('killing all processes')

        for process, pfield in cfg.items():

            if not isinstance(pfield, dict):
                continue
            
            kill(process, cfg)

        return


    pprint = print_utils.ProgressReporter.get_print_fn(process)
    verbose = config.ConfigOptions.verbose
    
    pfield = cfg[process]
    machine = pfield.get('machine', None)
    if machine == 'local':
        machine = None
    persistent = pfield.get('persistent', True)
    session = cfg['session']
    
    # connect to remote
    if machine is not None and machine not in connection_map.keys():
        pprint(f'opening ssh connection to remote {machine}')
        ssh = Connection(machine)
        connection_map[machine] = ssh 
    elif machine is not None:
        ssh = connection_map[machine]
    else:
        ssh = None 
        
    # look up dependant processes
    for pname, pfield in cfg.items():

        if pname == process:
            continue
        
        try:
            deps = pfield['depends']
        except:
            continue

        if process in deps:
            
            pprint(f'found dependant process {pname}')

            kill(pname, cfg)

    # non-persistent are just one shot commands
    if persistent:
        lsdict = remote.tmux_ls(ssh, session)
        if process not in lsdict.keys():
            pprint('not running')
        elif lsdict[process]['dead']:
            pprint('already dead')
        else:
            pprint('killing with SIGINT')
            pid = lsdict[process]['pid']
            remote.run_cmd(ssh, f'tmux send-keys -t {session}:{process} C-c C-m Enter',
                        interactive=False,
                        throw_on_failure=True) 
            attempts = 0
            while remote.tmux_session_alive(ssh, session, process):
                pprint('waiting for exit..')
                time.sleep(1)
                attempts += 1
                if attempts > 5:
                    pprint('killing with SIGKILL')
                    remote.run_cmd(ssh, f'tmux send-keys -t {session}:{process} C-\\\ C-m Enter',
                        interactive=False,
                        throw_on_failure=True) 

            
        
    

        

@print_utils.ProgressReporter.count_calls
def status(process, cfg):

    session = cfg['session']

    for process, pfield in cfg.items():

        if not isinstance(pfield, dict):
            continue

        pprint = print_utils.ProgressReporter.get_print_fn(process)
        verbose = config.ConfigOptions.verbose
        
        pfield = cfg[process]
        machine = pfield.get('machine', None)
        if machine == 'local':
            machine = None
        cmd = pfield['cmd']
        ready_check = pfield.get('ready_check', None)
        persistent = pfield.get('persistent', True)
        
        # connect to remote
        if machine is not None and machine not in connection_map.keys():
            pprint(f'opening ssh connection to remote {machine}')
            ssh = Connection(machine)
            connection_map[machine] = ssh 
        elif machine is not None:
            ssh = connection_map[machine]
        else:
            ssh = None

        remote.putfile(ssh, os.path.dirname(__file__) + "/print_ps_tree.py", '/tmp/concert_launcher_print_ps_tree.py')

        lsdict = remote.tmux_ls(ssh, session)

        try:

            pinfo = lsdict[process]

            if pinfo['dead']:
                pprint('dead')
                continue

            retcode, stdout, _ = remote.run_cmd(ssh,
                           f'python3 /tmp/concert_launcher_print_ps_tree.py {pinfo["pid"]}',
                           interactive=False,
                           throw_on_failure=True)
            
            pprint('process tree: ')
            print('  ', stdout.replace('\n', '\n  '))

        except:
            pass
    