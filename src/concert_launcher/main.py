import argparse
import argcomplete
import logging
import time
import os
import yaml
from typing import List, Dict

from concert_launcher import config
from concert_launcher import executor
from concert_launcher import monitoring_session

def do_main():

    # cmd line args
    parser = argparse.ArgumentParser(description='A minimal YAML and TMUX based process launcher')

    command = parser.add_subparsers(dest='command')
    command.required = True

    run = command.add_parser('run', help='run the specified process and its dependencies')
    
    run.add_argument('process', help='process name to run')

    run.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')

    run.add_argument('--monitor', '-m', action='store_true', help='spawn a local tmux monitoring session')

    run.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')

    kill = command.add_parser('kill', help='kill the specified process and its dependant packages')

    kill.add_argument('process', nargs='?', default=None, help='process name to run')

    kill.add_argument('--all', '-a', action='store_true', help='kill all processes')

    kill.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')

    kill.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')

    status = command.add_parser('status', help='show status information for all processes')

    status.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')

    status.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')
    
    mon = command.add_parser('mon', help='spawn a tmux monitoring session on the local machine')

    mon.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')

    mon.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')
    
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
    
    session = cfg['session']

    if args.command == 'run':

        # create local viewer
        if args.monitor:
            
            monitoring_session.create_monitoring_session(process=args.process, cfg=cfg)
            
            os.system(f'x-terminal-emulator -x "tmux a -t {session}_mon; bash"')

        # run processes
        executor.execute_process(process=args.process, cfg=cfg)

    if args.command == 'kill':

        proc_to_kill = None if args.all else args.process

        executor.kill(process=proc_to_kill, cfg=cfg)

    if args.command == 'status':

        executor.status(None, cfg=cfg)

    if args.command == 'mon':

        monitoring_session.create_monitoring_session(process=None, cfg=cfg)
        
        os.system(f'x-terminal-emulator -x "tmux a -t {session}_mon; bash"')


def main():

    do_main()
    
if __name__ == '__main__':
    main()