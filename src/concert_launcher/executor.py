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

# complete fn
async def notify_completed(process):
    async with completed_proc_cond:
        completed_proc.add(process)
        completed_proc_cond.notify_all()

class Variant:

        def __init__(self, name: str, cfg: dict):
            
            self.name = name
            
            vfield = cfg[name]

            self.choices = []

            self.params = {}

            self.cmd = {}

            if isinstance(vfield, list):
                for v in vfield:
                    self.choices.append(list(v.keys())[0])
                for i, c in enumerate(self.choices):
                    self.params[c] = vfield[i][c].get('params', {})
                    self.cmd[c] = vfield[i][c].get('cmd', None)
            else:
                self.choices = [name]
                self.params[name] = vfield.get('params', {})
                self.cmd[name] = vfield.get('cmd', None)
                        
            logger.debug(f'variant with name {name}')
            logger.debug(f'        with choices {self.choices}')
            logger.debug(f'        with params {self.params}')
            logger.debug(f'        with cmd {self.cmd}')


class ConfigParser:
    
    def __init__(self, process, cfg, level) -> None:

        # master cfg
        self.cfg = cfg
        
        # print with intentation to reflect dependency tree
        self.print = print_utils.ProgressReporter.get_print_fn(process, level)
        
        # not used atm
        self.verbose = config.ConfigOptions.verbose
        
        # parse config
        pfield = cfg[process]
        self.pfield = pfield

        # cmd needs calling parse_cmd()
        self.cmd = None 
        
        # parse remote machine (none = local machine)
        self.machine = pfield.get('machine', None)

        if self.machine == 'local':
            self.machine = None
        
        # cmd that returns 0 if proc is ready
        self.ready_check = pfield.get('ready_check', None)
        
        # not persistent means one shot command (does not stay alive)
        self.persistent = pfield.get('persistent', True)
        
        # session name for this proc (used to group procs into tmux sessions)
        self.session = pfield.get('session', cfg['context']['session'])
        
        # list of dependencies
        self.deps = pfield.get('depends', [])

        # parse variants
        self.variants = []
        
        if 'variants' in pfield.keys():
            for v in pfield['variants'].keys():
                var = Variant(v, pfield['variants'])
                self.variants.append(var)

        # save name
        self.name = process

        #

    
    def parse_cmd(self, user_params, user_variants):

        # start with global params + user params
        params = self.cfg['context'].get('params', {})
        params = dict(params)
        params.update(**user_params)
            
        # parse variants to update cmd and params
        cmd = self.pfield['cmd']

        for v in self.variants:
            v : Variant = v
            for vuser in user_variants:
                if vuser not in v.choices:
                    continue
                if v.cmd[vuser] is not None:
                    cmd = v.cmd[vuser]
                params.update(**v.params[vuser])

        # parse params
        try:
            self.cmd = cmd.format(**params)
        except KeyError as e:
            logger.error(f'{e}: specify missing params inside cfg.context.params or with --params key:=value')
            raise e

        # escape bash special chars
        self.cmd = self.cmd.replace('$', '\\$')


    async def connect(self):
        
        async with connection_map_lock:

            # connect to remote
            if self.machine is not None and self.machine not in connection_map.keys():
                self.print(f'opening ssh connection to remote {self.machine}')
                self.ssh = await self._connect()
                await self._upload_resources()
                connection_map[self.machine] = self.ssh 
            elif self.machine is not None:
                self.ssh = connection_map[self.machine]
            else:
                self.ssh = None 
                await self._upload_resources()


    async def _connect(self):
        
        user, host = self.machine.split('@')

        logger.info(f'waiting for ssh connection to {self.machine}')
        conn = await asyncssh.connect(host=host, username=user, request_pty='force')
        logger.info(f'created ssh connection to {self.machine}')

        return conn 
    

    async def _upload_resources(self):

        if self.machine is None:
            user, host = 'local_user', 'local_host'
        else:
            user, host = self.machine.split('@')
        
        resource_files = [
            "concert_launcher_wrapper.bash",
            "concert_launcher_print_ps_tree.py"
        ]
        
        has_resource_files = True 
        
        for rf in resource_files:
            logging.info(f'looking up /tmp/{rf} in {user}@{host}')
            ret, _, _, = await remote.run_cmd(self.ssh, f'ls /tmp/{rf}', throw_on_failure=False)
            if ret != 0:
                logging.info(f'looking up /tmp/{rf} in {user}@{host} -> NOT FOUND')
                has_resource_files = False 
                break

        # copy needed files to remote
        if not has_resource_files:
            logging.info('uploading resources')
            await remote.putfile(self.ssh, os.path.dirname(__file__) + "/resources/concert_launcher_wrapper.bash", '/tmp')
            await remote.putfile(self.ssh, os.path.dirname(__file__) + "/resources/concert_launcher_print_ps_tree.py", '/tmp')
            logging.info('uploading resources DONE')



async def execute_process(process, cfg, params={}, variants=[], level=0):

    # clear proc cache
    if level == 0:
        completed_proc.clear()
        pending_proc.clear()
    
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
        dep_coro_list.append(execute_process(dep, cfg, params, variants, level+1))

    if len(dep_coro_list) > 0:
        logger.info('waiting for dependencies..')
        await asyncio.gather(*dep_coro_list)
        logger.info('..ok')

    # shorthand
    ssh = e.ssh

    # non-persistent are just one shot commands
    if not e.persistent:
    
        e.print(f'running command')
        
        # parse cmdline
        e.parse_cmd(params, variants)
        
        # run
        exitcode, stdout, stderr = await remote.run_cmd(ssh, e.cmd, 
                                                        interactive=True, 
                                                        throw_on_failure=False)
        for l in stdout.split('\n'):
            e.print(f'[stdout] {l}')
        if exitcode != 0:
            e.print(f'failed (exit code {exitcode})')
        else:
            e.print(f'success')
        
        await notify_completed(process=process)
        return exitcode == 0
        
    # check already running
    session_exists = await remote.tmux_session_alive(ssh, e.session, process)
    
    if session_exists:
        e.print(f'exists')
    else:
        e.print(f'running process..')
    
        # parse cmdline
        e.parse_cmd(params, variants)
            
        # run
        await remote.tmux_spawn_new_session(ssh, e.session, process, e.cmd)
        e.print('..done')

    # ready check
    if e.ready_check is not None:

        while True:
            
            t0 = time.time()

            e.print('checking for readiness')

            retcode, _, _ = await remote.run_cmd(ssh, e.ready_check, interactive=True, throw_on_failure=False)

            if not await remote.tmux_session_alive(ssh, e.session, process):
                raise RuntimeError(f'process {e.session}:{process} no longer exists')
            
            if retcode == 0:
                logger.info(f'ready check for process {process} returned 0')
                break

            to_sleep = 0.666 - (time.time() - t0)  # at least 1 sec
            
            await asyncio.sleep(to_sleep)


    e.print(f'ready')
    await notify_completed(process=process)
    return True


async def kill(process, cfg, level=0, graceful=True):

    # clear proc cache
    if level == 0:
        completed_proc.clear()
        pending_proc.clear()

    # if process is none, kill all
    if process is None:
        
        pprint = print_utils.ProgressReporter.get_print_fn('all', level=0)

        pprint('will kill all processes')

        proc_coro_list = []

        for process, pfield in cfg.items():

            if process == 'context':
                continue
            
            proc_coro_list.append(kill(process, cfg, level=level+1, graceful=graceful))

        await asyncio.gather(*proc_coro_list)
        return True
    

    # await for process completion if pending
    if process in pending_proc:
        
        logging.info(f'process {process} pending; waiting for completion..')
        
        def is_completed():
            return process in completed_proc
        
        async with completed_proc_cond:
            await completed_proc_cond.wait_for(is_completed)

        return True
    
    logger.info(f'kill {process}')

    # add to pending
    pending_proc.add(process)

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
            logger.info(f'{pname} has no dependencies')
            continue

        if process in deps and pfield.get('persistent', True):
            
            e.print(f'found dependant process {pname}')
            proc_coro_list.append(kill(pname, cfg, level+1, graceful=graceful))

    # wait until all killed
    if len(proc_coro_list) > 0:
        await asyncio.gather(*proc_coro_list)
        proc_coro_list.clear()

    # non-persistent are just one shot commands,
    # we use them as process groups and kill dependencies
    if not e.persistent:
        
        for dep in e.deps:
            proc_coro_list.append(kill(dep, cfg, level+1))
        
        # wait until all killed
        if len(proc_coro_list) > 0:
            e.print('killing dependencies')
            await asyncio.gather(*proc_coro_list)
            proc_coro_list.clear()
            
        await notify_completed(process=process)
        return True

    # get list of running windows
    lsdict = await remote.tmux_ls(e.ssh, e.session)

    if process not in lsdict.keys():
        e.print('not running')
        await notify_completed(process=process)
        return True

    if lsdict[process]['dead']:
        e.print('already dead')
        await notify_completed(process=process)
        return True
    
    signame = 'SIGINT' if graceful else 'SIGKILL'
    sigkey = 'C-c' if graceful else 'C-\\\ '
        
    e.print(f'killing with {signame}')

    pid = lsdict[process]['pid']

    # send CTRL+C
    await remote.run_cmd(e.ssh, f'tmux send-keys -t {e.session}:{process} {sigkey} C-m Enter',
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
    await notify_completed(process=process)
    return True


async def status(process, cfg):

    status_dict = {}

    proc_cfg = {}

    for process, pfield in cfg.items():

        if process == 'context':
            continue

        e = ConfigParser(process=process, cfg=cfg, level=0)

        proc_cfg[process] = e
        
        await e.connect()

        lsdict = await remote.tmux_ls(e.ssh, e.session)

        status_dict[e.session] = lsdict

    print()

    for s, sdict in status_dict.items():

        for p, pdict in sdict.items():
            
            status = 'DEAD   ' if pdict['dead'] else 'RUNNING'
            pid = pdict['pid']
            ret = pdict['exitstatus']
            e = proc_cfg[p]
            machine = 'local' if e.machine is None else e.machine

            print(f'{p :<15}\t{s}\t{machine :<20}\t{status}\t{pid}\t{ret}')

    return status_dict



            
async def pstree(process, cfg, level=0):
    
    tasks = []

    status_dict = {}

    for process, pfield in cfg.items():

        if process == 'context':
            continue

        e = ConfigParser(process=process, cfg=cfg, level=0)
        
        await e.connect()

        ssh = e.ssh

        # get list of running windows
        lsdict = await remote.tmux_ls(ssh, e.session)

        status_dict[e.session] = lsdict

        try:
            
            # this fails if windows does not exist
            pinfo = lsdict[process]

            if pinfo['dead']:
                e.print('dead')
                continue
            
            logging.info(f'adding task for process {process}')
            
            tasks.append(_pstree(e, pinfo['pid']))

        except:
            pass
        
    logging.info('awaiting results')
        
    res = await asyncio.gather(*tasks)
    
    for r in res:
        r()

    return status_dict
    
    
async def _pstree(e: ConfigParser, pid):
        
    # get process tree
    _, stdout, _ = await remote.run_cmd(
                    e.ssh,
                    f'python3 /tmp/concert_launcher_print_ps_tree.py {pid}')
    
    def printer():
        e.print('process tree: ')
        print('  ', stdout.replace('\n', '\n  '))
    
    return printer


# class for printing each process stdout
# with a nice prefix
class Printer:
    def __init__(self, process) -> None:
        self.process = process
    async def print(self,l):
        print('[', self.process, ']', l, end='')

        
def default_get_printer(process):
    return Printer(process).print


# watch proc stdout
async def watch(process: str, cfg: Dict, printer_coro_factory=default_get_printer):

    # process is none = watch all
    if process is None:

        tasks = []

        for process, _ in cfg.items():

            if process == 'context':
                continue

            e = ConfigParser(process=process, cfg=cfg, level=0)
            
            await e.connect()

            watch_coro = remote.watch_process(e.ssh, 
                                              f'touch /tmp/{process}.stdout && tail -f -n +1 /tmp/{process}.stdout', 
                                              stdout_coro=printer_coro_factory(process))

            tasks.append(watch_coro)

        await asyncio.gather(*tasks)

        return


    e = ConfigParser(process, cfg, 0)

    await e.connect()

    await remote.watch_process(e.ssh, 
                        f'tail -f -n +1 /tmp/{process}.stdout', 
                        stdout_coro=printer_coro_factory(process))