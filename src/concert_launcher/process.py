"""Configuration parsing for one managed process."""

import inspect
import logging

from .connections import default_connection_manager
from .errors import ConfigurationError
from .output import ProgressReporter
from .resources import ensure_resources

logger = logging.getLogger(__name__)


class Variant:
    def __init__(self, name, variants_config):
        self.name = name
        field = variants_config[name]
        self.choices = []
        self.params = {}
        self.commands = {}

        if isinstance(field, list):
            for item in field:
                if len(item) != 1:
                    raise ConfigurationError(
                        "variant group {!r} entries must contain one choice".format(name)
                    )
                choice = next(iter(item))
                choice_config = item[choice] or {}
                self.choices.append(choice)
                self.params[choice] = choice_config.get("params", {})
                self.commands[choice] = choice_config.get("cmd")
        else:
            field = field or {}
            self.choices = [name]
            self.params[name] = field.get("params", {})
            self.commands[name] = field.get("cmd")


class ConfigParser:
    """Parsed view of a single process configuration.

    The historical class name is retained for compatibility. New code should
    normally use :class:`concert_launcher.Launcher` instead.
    """

    def __init__(
        self,
        process,
        cfg,
        notify_ev_callback=None,
        level=0,
        connection_manager=None,
        reporter=None,
    ):
        if process not in cfg or process == "context":
            raise ConfigurationError("unknown process {!r}".format(process))
        if "context" not in cfg or "session" not in cfg["context"]:
            raise ConfigurationError("configuration requires context.session")

        self.cfg = cfg
        self.name = process
        self.level = level
        self.notify_ev_callback = notify_ev_callback
        self.connection_manager = connection_manager or default_connection_manager
        self.reporter = reporter
        self.print_fn = ProgressReporter.get_print_fn(process, level)

        self.pfield = cfg[process] or {}
        if "cmd" not in self.pfield:
            raise ConfigurationError("process {!r} requires cmd".format(process))

        self.machine = self.pfield.get("machine")
        if self.machine == "local":
            self.machine = None
        self.docker = self.pfield.get("docker")
        self.ready_check = self.pfield.get("ready_check")
        self.persistent = self.pfield.get("persistent", True)
        self.session = self.pfield.get("session", cfg["context"]["session"])
        self.deps = list(self.pfield.get("depends", []))
        self.force_sigquit = self.pfield.get("force_sigquit", False)
        self.variants = [
            Variant(name, self.pfield.get("variants", {}))
            for name in self.pfield.get("variants", {})
        ]
        self.cmd = None
        self.ssh = None

    async def print(self, text, **kwargs):
        del kwargs
        if self.notify_ev_callback is not None:
            result = self.notify_ev_callback(self.name, text)
            if inspect.isawaitable(result):
                await result
        if self.reporter is not None:
            self.reporter.event(self.name, self.level, text)
        else:
            self.print_fn(text)

    async def notify_state(self, state):
        if self.notify_ev_callback is not None:
            result = self.notify_ev_callback(self.name, "state is {}".format(state))
            if inspect.isawaitable(result):
                await result

    def parse_cmd(self, user_params=None, user_variants=None):
        params = dict(self.cfg["context"].get("params", {}))
        params.update(user_params or {})
        command = self.pfield["cmd"]

        selected = set(user_variants or [])
        for variant in self.variants:
            matches = selected.intersection(variant.choices)
            if len(matches) > 1:
                raise ConfigurationError(
                    "variant group {!r} selected more than once: {}".format(
                        variant.name, sorted(matches)
                    )
                )
            if not matches:
                continue
            choice = next(iter(matches))
            replacement = variant.commands[choice]
            if replacement is not None:
                command = replacement.replace("{cmd}", command)
            params.update(variant.params[choice])

        try:
            command = command.format(**params)
        except KeyError as exc:
            raise ConfigurationError(
                "missing parameter {} for process {!r}".format(exc, self.name)
            ) from exc

        command = command.replace("$", "\\$").replace('"', '\\"')
        if self.docker is not None:
            command = 'docker exec -it {} bash -ic \\"{}\\"'.format(
                self.docker, command
            )
            if self.ready_check is not None:
                self.ready_check = 'docker exec -it {} bash -ic "{}"'.format(
                    self.docker, self.ready_check
                )
        self.cmd = command
        return command

    async def connect(self, announce=True):
        self.ssh = await self.connection_manager.get(self.machine)
        if announce:
            await self.print(
                "using local machine"
                if self.machine is None
                else "connected to {}".format(self.machine)
            )
        await ensure_resources(self.ssh)
        return True
