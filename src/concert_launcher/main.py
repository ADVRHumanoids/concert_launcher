import argparse
import argcomplete
import logging
import os
import yaml
from typing import List, Dict

from concert_launcher import config
from concert_launcher import executor
from concert_launcher import monitoring_session

def do_main():

    # cmd line args
    parser = argparse.ArgumentParser(description='cose')

    parser.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='set the logging level')

    command = parser.add_subparsers(dest='command')

    run = command.add_parser('run', help='run the specified process and its dependencies')
    
    run.add_argument('process', help='process name to run')

    run.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')

    run.add_argument('--monitor', '-m', action='store_true', help='create a local tmux monitoring session')

    kill = command.add_parser('kill', help='send signal to the specified process and its dependant packages')

    kill.add_argument('process', help='process name to run')

    kill.add_argument('--config', '-c', default='./launcher.yaml', type=str, help='path config file')
    
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

    if args.command == 'run':

        # create local viewer
        if args.monitor:
            monitoring_session.create_monitoring_session(process=args.process, cfg=cfg)

        # run processes
        executor.execute_process(process=args.process, cfg=cfg)

    if args.command == 'kill':

        executor.kill(process=args.process, cfg=cfg)


def main():
    do_main()
    

if __name__ == '__main__':
    main()