import argparse
import argcomplete
import logging
import os
import yaml
from typing import List, Dict

from concert_launcher import config
from concert_launcher import executor

def do_main():

    # cmd line args
    parser = argparse.ArgumentParser(description='cose')
    
    parser.add_argument('process', help='process name to run')
    parser.add_argument('--config', '-c', required=True, type=str, help='path config file')
    parser.add_argument('--log-level', '-l', dest='log_level', default='WARNING', 
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='Set the logging level (default: INFO)')
        
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

    executor.execute_process(process=args.process, cfg=cfg)


def main():
    do_main()
    

if __name__ == '__main__':
    main()