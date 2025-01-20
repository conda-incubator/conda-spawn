"""
conda pip subcommand for CLI
"""

from __future__ import annotations

import argparse
import os
from textwrap import dedent

from conda.exceptions import CondaError, ArgumentError
from conda.cli.conda_argparse import (
    add_parser_help,
    add_parser_prefix,
)


def configure_parser(parser: argparse.ArgumentParser):
    from .shell import SHELLS

    add_parser_help(parser)
    add_parser_prefix(parser, prefix_required=True)

    parser.add_argument(
        "command",
        metavar="COMMAND [args]",
        nargs="*",
        help="Optional program to run after starting the shell. "
        "Use -- before the program if providing arguments.",
    )
    shell_group = parser.add_argument_group("Shell options")
    shell_group.add_argument(
        "--hook",
        action="store_true",
        help=(
            "Print the shell activation logic so it can be sourced in-process. "
            "This is meant to be used in scripts only."
        ),
    )
    shell_group.add_argument(
        "--shell",
        choices=SHELLS,
        help="Shell to use for the new session. If not specified, autodetect shell in use.",
    )
    shell_group.add_argument(
        "--replace",
        action="store_true",
        help="Spawning shells within conda-spawn shells is disallowed by default. "
        "This flag enables nested spawns by replacing the activated environment.",
    )
    shell_group.add_argument(
        "--stack",
        action="store_true",
        help="Spawning shells within conda-spawn shells is disallowed by default. "
        "This flag enables nested spawns by stacking the newly activated environment "
        "on top of the current one.",
    )

    parser.prog = "conda spawn"
    parser.epilog = dedent(
        """
        Examples for --hook usage in different shells:
          POSIX:
            source "$(conda spawn --hook -n ENV-NAME)"
          CMD:
            FOR /F "tokens=*" %%g IN ('conda spawn --hook -n ENV-NAME') do @CALL %%g
          Powershell:
            conda spawn --hook -n ENV-NAME | Out-String | Invoke-Expression
        """
    ).lstrip()


def execute(args: argparse.Namespace) -> int:
    from .main import (
        hook,
        spawn,
        environment_speficier_to_path,
        shell_specifier_to_shell,
    )

    if args.stack and args.replace:
        raise ArgumentError(
            "--stack and --replace are mutually exclusive. Choose only one."
        )
    if (
        os.getenv("CONDA_SPAWN", "0") not in ("", "0")
        and not args.replace
        and not args.stack
    ):
        if current_env := os.getenv("CONDA_PREFIX"):
            env_info = f" for environment '{current_env}'"
        else:
            env_info = ""
        raise CondaError(
            dedent(
                f"""
                Detected active 'conda spawn' session{env_info}.
                Nested activation is disallowed by default.
                Please exit the current session before starting a new one by running 'exit'.
                Alternatively, check the usage of --replace and/or --stack.
                """
            ).lstrip()
        )

    prefix = environment_speficier_to_path(args.name, args.prefix)
    shell = shell_specifier_to_shell(args.shell)
    if args.hook:
        if args.command:
            raise ArgumentError("COMMAND cannot be provided with --hook.")
        return hook(prefix, shell, stack=args.stack)
    return spawn(prefix, shell, stack=args.stack, command=args.command)
