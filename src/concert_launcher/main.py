"""Console entry point."""

import asyncio
import logging
import os
import sys
import time

from . import monitoring_session
from .cli import (
    build_parser,
    default_config_path,
    load_config,
    parse_assignments,
    process_choices,
)
from .errors import LauncherError, RemoteConnectionError
from .launcher import Launcher
from .output import ConsoleReporter, cli_color_enabled


async def do_main(argv=None):
    config_path = default_config_path()
    parser = build_parser(config_path, process_choices(config_path))
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    config = load_config(os.path.abspath(args.config) if args.config else None)
    launcher = Launcher(
        config,
        reporter=ConsoleReporter(
            stream=sys.stdout,
            color=cli_color_enabled(sys.stdout),
        ),
    )
    session = config["context"]["session"]

    def spawn_monitor():
        if args.command == "mon" and args.replace:
            os.execvpe(
                "bash",
                ["bash", "-ic", "tmux attach -t {}_mon".format(session)],
                os.environ,
            )
        os.system(
            'x-terminal-emulator -x "tmux a -t {0}_mon; bash"'.format(session)
        )

    try:
        if args.command == "run":
            params = parse_assignments(args.params, "--params")
            variants = args.variants or []
            if args.monitor:
                await monitoring_session.create_monitoring_session(
                    process=args.process, cfg=config
                )
                spawn_monitor()
            if args.ssh_retries:
                success = await launcher.execute_with_recovery(
                    args.process,
                    params=params,
                    variants=variants,
                    retries=args.ssh_retries,
                )
            else:
                success = await launcher.execute_process(
                    args.process, params=params, variants=variants
                )
            if args.watch and success:
                return await launcher.wait_process(args.process)
            return 0 if success else 1

        if args.command == "kill":
            target = None if args.all else args.process
            success = await launcher.kill(target, graceful=not args.force)
            return 0 if success else 1

        if args.command == "status":
            if args.watch:
                while True:
                    started = time.monotonic()
                    if args.pstree:
                        await launcher.pstree(args.process)
                    else:
                        await launcher.status(
                            args.process,
                            print_to_stdout=True,
                            raise_on_unavailable=False,
                        )
                    print()
                    await asyncio.sleep(
                        max(0.0, 1.0 - (time.monotonic() - started))
                    )
            elif args.pstree:
                await launcher.pstree(args.process)
            else:
                await launcher.status(
                    args.process,
                    print_to_stdout=True,
                    raise_on_unavailable=False,
                )
            return 0

        if args.command == "mon":
            await monitoring_session.create_monitoring_session(
                process=None, cfg=config
            )
            spawn_monitor()
            return 0

        if args.command == "watch":
            await launcher.watch(args.process, num_lines=args.num_lines)
            return 0

        parser.error("unknown command {!r}".format(args.command))
    finally:
        await launcher.close()


def main(argv=None):
    try:
        return asyncio.get_event_loop().run_until_complete(do_main(argv))
    except KeyboardInterrupt:
        return 130
    except RemoteConnectionError as exc:
        print("Remote host unavailable: {}".format(exc), file=sys.stderr)
        print(
            "Retry the command, use --ssh-retries, or call Launcher.recover() "
            "from the asyncio API.",
            file=sys.stderr,
        )
        return 2
    except LauncherError as exc:
        print("concert_launcher: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
