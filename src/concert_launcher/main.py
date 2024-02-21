import argparse
import argcomplete
import logging
import time
import os
import yaml
from typing import List, Dict
import asyncio

import warnings
from cryptography.utils import CryptographyDeprecationWarning
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
    import paramiko

from concert_launcher import config
from concert_launcher import executor
from concert_launcher import monitoring_session

async def do_main():

    # try to parse default config to provide process choices
    # note: a local file named launcher.yaml has precendence over the env variable
    if os.path.exists('./launcher.yaml'):
        dfl_config_path = './launcher.yaml'
    else:
        dfl_config_path = os.environ.get('CONCERT_LAUNCHER_DEFAULT_CONFIG', None)
    
    process_choices = None
    
    try:
        dfl_config = yaml.safe_load(open(dfl_config_path, 'r'))
        process_choices = [pname for pname in dfl_config.keys() if pname != 'context']
    except:
        pass
        

    # cmd line args
    parser = argparse.ArgumentParser(description='A minimal YAML and TMUX based process launcher')

    command = parser.add_subparsers(dest='command')

    command.required = True
    
    # run
    run = command.add_parser('run', help='run the specified process and its dependencies')
    
    run.add_argument('process', choices=process_choices, help='process name to run')

    run.add_argument('--config', '-c', default=dfl_config_path, type=str, help='path config file')

    run.add_argument('--monitor', '-m', action='store_true', help='spawn a local tmux monitoring session')

    run.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')

    # kill
    kill = command.add_parser('kill', help='kill the specified process and its dependant packages')

    kill.add_argument('process', choices=process_choices, nargs='?', default=None, help='process name to run')

    kill.add_argument('--all', '-a', action='store_true', help='kill all processes')

    kill.add_argument('--config', '-c', default=dfl_config_path, type=str, help='path config file')

    kill.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')

    # status
    status = command.add_parser('status', help='show status information for all processes')

    status.add_argument('--config', '-c', default=dfl_config_path, type=str, help='path config file')

    status.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')
    
    mon = command.add_parser('mon', help='spawn a tmux monitoring session on the local machine')

    mon.add_argument('--replace', '-r', action='store_true', help='run monitoring session in current shell')

    mon.add_argument('--config', '-c', default=dfl_config_path, type=str, help='path config file')

    mon.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')
    
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    # convert log level string to corresponding numeric value
    log_level = getattr(logging, args.log_level.upper())

    config.ConfigOptions.verbose = log_level < getattr(logging, 'WARNING')

    # logger
    logger = logging.getLogger(__name__)

    # configure logging with the specified level
    logging.basicConfig(level=log_level)

    # load config
    config_path = os.path.abspath(args.config)

    logger.info(f'loading config {config_path}')

    cfg = yaml.safe_load(open(config_path))
    
    session = cfg['context']['session']

    def spawn_monitor():
        if args.command == 'mon' and args.replace:
            os.execvpe('bash', ['bash', '-ic', f'tmux attach -t {session}_mon'], env=os.environ)
        else:
            os.system(f'x-terminal-emulator -x "tmux a -t {session}_mon; bash"')

    if args.command == 'run':

        # create local viewer
        if args.monitor:

            await monitoring_session.create_monitoring_session(process=args.process, cfg=cfg)
            
            spawn_monitor()

        # run processes
        await executor.execute_process(process=args.process, cfg=cfg)

    if args.command == 'kill':

        proc_to_kill = None if args.all else args.process
        
        logger.info(f'will kill proc {proc_to_kill}')

        await executor.kill(process=proc_to_kill, cfg=cfg)

    if args.command == 'status':

        await executor.status(None, cfg=cfg)

    if args.command == 'mon':

        await monitoring_session.create_monitoring_session(process=None, cfg=cfg)
        
        spawn_monitor()

    
def main():

    asyncio.get_event_loop().run_until_complete(do_main())
    

if __name__ == '__main__':
    main()