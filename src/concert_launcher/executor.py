from typing import List, Dict
import os
import logging
from fabric import Connection
from concert_launcher import print_utils, config, remote

logger = logging.getLogger(__name__)

connection_map : Dict[str, Connection] = dict()

@print_utils.ProgressReporter.count_calls
def execute_process(process, cfg):

    pprint = print_utils.ProgressReporter.get_print_fn(process)
    verbose = config.ConfigOptions.verbose
    
    pfield = cfg[process]
    machine = pfield['machine']
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
    if machine not in connection_map.keys():
        pprint(f'opening ssh connection to remote {machine}')
        ssh = Connection(machine)
        ssh.put(os.path.dirname(__file__) + "/concert_launcher_wrapper.bash", '/tmp')
        connection_map[machine] = ssh 
    else:
        ssh = connection_map[machine]

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
        logger.info(f'process {process} is already running')

    else:
        pprint(f'running process')
        logger.info(f'running process {process}')
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


    logger.info(f'{process} is ready')
    pprint(f'ready')