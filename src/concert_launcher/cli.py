"""Command-line parsing helpers."""

import argparse
import os

import argcomplete
import yaml

from .errors import ConfigurationError


def default_config_path():
    configured = os.environ.get("CONCERT_LAUNCHER_DEFAULT_CONFIG")
    if configured:
        return os.path.abspath(configured)
    local_path = os.path.abspath("launcher.yaml")
    if os.path.exists(local_path):
        return local_path
    return None


def load_config(path):
    if not path:
        raise ConfigurationError(
            "no configuration found; use --config or set "
            "CONCERT_LAUNCHER_DEFAULT_CONFIG"
        )
    try:
        with open(path, "r") as stream:
            config = yaml.safe_load(stream)
    except OSError as exc:
        raise ConfigurationError("cannot read config {}: {}".format(path, exc)) from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError("invalid YAML in {}: {}".format(path, exc)) from exc
    if not isinstance(config, dict):
        raise ConfigurationError("configuration root must be a mapping")
    return config


def process_choices(path):
    try:
        config = load_config(path)
    except ConfigurationError:
        return None
    return sorted(name for name in config if name != "context")


def parse_assignments(values, option_name):
    result = {}
    for value in values or []:
        if ":=" not in value:
            raise ConfigurationError(
                "{} expects key:=value, got {!r}".format(option_name, value)
            )
        key, item = value.split(":=", 1)
        if not key:
            raise ConfigurationError(
                "{} expects a non-empty key, got {!r}".format(option_name, value)
            )
        result[key] = item
    return result


def build_parser(config_path=None, choices=None):
    parser = argparse.ArgumentParser(
        description="Launch dependency graphs locally, over SSH, and in Docker"
    )
    commands = parser.add_subparsers(dest="command")
    commands.required = True

    def add_common(command):
        command.add_argument(
            "--config", "-c", default=config_path, help="path to launcher YAML"
        )
        command.add_argument(
            "--log-level",
            "-l",
            default="WARNING",
            choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        )

    run = commands.add_parser("run", help="start a process and its dependencies")
    run.add_argument("process", choices=choices)
    run.add_argument("--watch", "-w", action="store_true")
    run.add_argument("--params", "-p", nargs="+")
    run.add_argument("--variants", "-v", nargs="+")
    run.add_argument("--monitor", "-m", action="store_true")
    run.add_argument(
        "--ssh-retries",
        type=int,
        default=0,
        help="reconnect and retry after an SSH transport failure",
    )
    add_common(run)

    kill = commands.add_parser("kill", help="stop a process and its dependants")
    kill.add_argument("process", choices=choices, nargs="?", default=None)
    kill.add_argument("--all", "-a", action="store_true")
    kill.add_argument("--force", action="store_true", help="skip graceful SIGINT")
    add_common(kill)

    status = commands.add_parser("status", help="show process status")
    status.add_argument("process", choices=choices, nargs="?", default=None)
    status.add_argument("--watch", "-w", action="store_true")
    status.add_argument("--pstree", "-t", action="store_true")
    add_common(status)

    monitor = commands.add_parser("mon", help="create a tmux monitoring session")
    monitor.add_argument("--replace", "-r", action="store_true")
    add_common(monitor)

    watch = commands.add_parser("watch", help="stream process output")
    watch.add_argument("process", choices=choices, nargs="?", default=None)
    watch.add_argument("--num-lines", "-n", default="+1")
    add_common(watch)

    argcomplete.autocomplete(parser)
    return parser
