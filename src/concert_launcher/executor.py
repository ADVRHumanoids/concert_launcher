from typing import List, Dict
import os
import logging
import time
from concert_launcher import print_utils, config, remote
import asyncssh
import asyncio

logger = logging.getLogger(__name__)

# dict holding ssh connections (to avoid repeating them)
connection_map : Dict[str, asyncssh.SSHClientConnection] = dict()
connection_map_lock = asyncio.Lock()

# pending procs = processes that are being started
pending_proc = set()

# completed procs = processes that were successfully started
completed_proc = set()
completed_proc_cond = asyncio.Condition()


class ConfigParser:

    def __init__(self, process, cfg, level) -> None:
        
        self.print = print_utils.ProgressReporter.get_print_fn(process, level)
        
        self.verbose = config.ConfigOptions.verbose
        
        # parse config
        pfield = cfg[process]
        
        self.machine = pfield.get('machine', None)

        if self.machine == 'local':
            self.machine = None
        
        self.cmd = pfield['cmd']

        # escape bash special chars
        self.cmd = self.cmd.replace('$', '\\$')
        
        self.ready_check = pfield.get('ready_check', None)
        
        self.persistent = pfield.get('persistent', True)
        
        self.session = pfield.get('session', cfg['context']['session'])
        
        self.deps = pfield.get('depends', [])


    async def connect(self):
        
        async with connection_map_lock:

            # connect to remote
            if self.machine is not None and self.machine not in connection_map.keys():
                self.print(f'opening ssh connection to remote {self.machine}')
                self.ssh = await self._connect()
                connection_map[self.machine] = self.ssh 
            elif self.machine is not None:
                self.ssh = connection_map[self.machine]
            else:
                self.ssh = None 


    async def _connect(self):
        
        user, host = self.machine.split('@')

        logger.info(f'waiting for ssh connection to {self.machine}')
        conn = await asyncssh.connect(host=host, username=user, request_pty='force')
        logger.info(f'created ssh connection to {self.machine}')
        return conn


async def execute_process(process, cfg, level=0):
    
    # await for process completion if pending
    if process in pending_proc:
        
        logging.info(f'process {process} pending; waiting for completion..')
        
        def is_completed():
            return process in completed_proc
        
        async with completed_proc_cond:
            await completed_proc_cond.wait_for(is_completed)

        return
    
    # add to pending
    pending_proc.add(process)

    # parse config
    e = ConfigParser(process=process, cfg=cfg, level=level)

    # connect ssh
    await e.connect()

    # process dependencies
    dep_coro_list = []

    for dep in e.deps:
        e.print(f'depends on {dep}')
        dep_coro_list.append(execute_process(dep, cfg, level+1))

    if len(dep_coro_list) > 0:
        logger.info('waiting for dependencies..')
        await asyncio.gather(*dep_coro_list)
        logger.info('..ok')

    # shorthand
    ssh = e.ssh

    # copy needed files to remote
    await remote.putfile(ssh, os.path.dirname(__file__) + "/concert_launcher_wrapper.bash", '/tmp')

    logging.info('copied resources OK')

    # non-persistent are just one shot commands
    if not e.persistent:
        e.print(f'running command')
        exitcode, stdout, stderr = await remote.run_cmd(ssh, e.cmd)
        for l in stdout.split('\n'):
            e.print(f'[stdout] {l}')
        if exitcode != 0:
            e.print(f'failed (exit code {exitcode})')
        else:
            e.print(f'success')
        return
        
    # check already running
    session_exists = await remote.tmux_session_alive(ssh, e.session, process)
    
    if session_exists:
        e.print(f'exists')
    else:
        e.print(f'running process')
        await remote.tmux_spawn_new_session(ssh, e.session, process, e.cmd)

    # ready check
    if e.ready_check is not None:


        while True:
            
            t0 = time.time()

            e.print('checking for readiness')

            retcode, _, _ = await remote.run_cmd(ssh, e.ready_check)

            if not await remote.tmux_session_alive(ssh, e.session, process):
                raise RuntimeError(f'process {e.session}:{process} no longer exists')
            
            if retcode == 0:
                logger.info(f'ready check for process {process} returned 0')
                break

            to_sleep = 1.0 - (time.time() - t0)  # at least 1 sec
            
            await asyncio.sleep(to_sleep)


    e.print(f'ready')
    async with completed_proc_cond:
        completed_proc.add(process)
        completed_proc_cond.notify_all()


async def kill(process, cfg, level=0):

    # if process is none, kill all
    if process is None:
        
        pprint = print_utils.ProgressReporter.get_print_fn('all', level=0)

        pprint('will kill all processes')

        proc_coro_list = []

        for process, pfield in cfg.items():

            if process == 'context':
                continue
            
            proc_coro_list.append(kill(process, cfg))

        return await asyncio.gather(*proc_coro_list)
    

    # await for process completion if pending
    if process in pending_proc:
        
        logging.info(f'process {process} pending; waiting for completion..')
        
        def is_completed():
            return process in completed_proc
        
        async with completed_proc_cond:
            await completed_proc_cond.wait_for(is_completed)

        return
    

    # add to pending
    pending_proc.add(process)

    # complete fn
    async def notify_completed():
        async with completed_proc_cond:
            completed_proc.add(process)
            completed_proc_cond.notify_all()

    # parse config and connect ssh
    e = ConfigParser(process=process, cfg=cfg, level=level)
    await e.connect()
        
    # look up dependant processes
    proc_coro_list = []

    for pname, pfield in cfg.items():

        if pname == process or pname == 'context':
            continue
        
        try:
            deps = pfield['depends']
        except:
            continue

        if process in deps:
            
            e.print(f'found dependant process {pname}')
            proc_coro_list.append(kill(pname, cfg, level+1))

    # wait until all killed
    if len(proc_coro_list) > 0:
        await asyncio.gather(*proc_coro_list)

    # non-persistent are just one shot commands
    if not e.persistent:
        return await notify_completed() 

    # get list of running windows
    lsdict = await remote.tmux_ls(e.ssh, e.session)

    if process not in lsdict.keys():
        e.print('not running')
        return await notify_completed() 

    if lsdict[process]['dead']:
        e.print('already dead')
        return await notify_completed() 
        
    e.print('killing with SIGINT')

    pid = lsdict[process]['pid']

    # send CTRL+C
    await remote.run_cmd(e.ssh, f'tmux send-keys -t {e.session}:{process} C-c C-m Enter',
                   interactive=False,
                   throw_on_failure=True) 
    
    attempts = 0

    # wait for exit, possibly escalate to CTRL+\
    while await remote.tmux_session_alive(e.ssh, e.session, process):
        e.print('waiting for exit..')
        await asyncio.sleep(1)
        attempts += 1
        if attempts > 5:
            e.print('killing with SIGKILL')
            await remote.run_cmd(e.ssh, f'tmux send-keys -t {e.session}:{process} C-\\\ C-m Enter',
                                 interactive=False,
                                 throw_on_failure=True) 
    e.print('killed')
    return await notify_completed() 

            
async def status(process, cfg, level=0):

    for process, pfield in cfg.items():

        if process == 'context':
            continue

        e = ConfigParser(process=process, cfg=cfg, level=0)
        await e.connect()

        ssh = e.ssh

        # copy required files to remote
        await remote.putfile(ssh, 
                             os.path.dirname(__file__) + "/print_ps_tree.py", 
                             '/tmp/concert_launcher_print_ps_tree.py')

        # get list of running windows
        lsdict = await remote.tmux_ls(ssh, e.session)

        try:
            
            # this fails if windows does not exist
            pinfo = lsdict[process]

            if pinfo['dead']:
                e.print('dead')
                continue
            
            # print process tree
            retcode, stdout, _ = await remote.run_cmd(ssh,
                           f'python3 /tmp/concert_launcher_print_ps_tree.py {pinfo["pid"]}',
                           interactive=False,
                           throw_on_failure=True)
            
            e.print('process tree: ')
            print('  ', stdout.replace('\n', '\n  '))

        except:
            pass
    