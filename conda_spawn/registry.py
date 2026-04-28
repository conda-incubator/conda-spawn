"""
Single source of truth for the `name -> Shell class` mapping used by the
CLI (`--shell`), the public `spawn`/`hook` entrypoints, and shell
auto-detection via `shellingham`.
"""

from __future__ import annotations

import sys
from logging import getLogger

import shellingham

from .shell import (
    BashShell,
    CmdExeShell,
    PosixShell,
    PowershellShell,
    Shell,
    ZshShell,
)
from .contrib import CshShell, FishShell, TcshShell, XonshShell

log = getLogger(f"conda.{__name__}")

SHELLS: dict[str, type[Shell]] = {
    "ash": PosixShell,
    "bash": BashShell,
    "cmd.exe": CmdExeShell,
    "cmd": CmdExeShell,
    "csh": CshShell,
    "dash": PosixShell,
    "fish": FishShell,
    "posix": PosixShell,
    "powershell": PowershellShell,
    "pwsh": PowershellShell,
    "tcsh": TcshShell,
    "xonsh": XonshShell,
    "zsh": ZshShell,
}


def default_shell_class() -> type[Shell]:
    if sys.platform == "win32":
        return CmdExeShell
    return PosixShell


def detect_shell_class() -> type[Shell]:
    try:
        name, _ = shellingham.detect_shell()
    except shellingham.ShellDetectionFailure:
        return default_shell_class()
    try:
        return SHELLS[name]
    except KeyError:
        log.warning("Did not recognize shell %s, returning default.", name)
        return default_shell_class()
