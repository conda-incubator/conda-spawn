from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import struct
import sys
from tempfile import NamedTemporaryFile
from logging import getLogger
from pathlib import Path
from typing import Iterable

if sys.platform != "win32":
    import fcntl
    import termios

    import pexpect

import shellingham

from . import activate


log = getLogger(f"conda.{__name__}")


class Shell:
    Activator: activate._Activator

    def __init__(self, prefix: Path, stack: bool = False):
        self.prefix = prefix
        self._prefix_str = str(prefix)
        self._stack = stack
        self._activator_args = ["activate"]
        if self._stack:
            self._activator_args.append("--stack")
        self._activator_args.append(str(prefix))
        self._activator = self.Activator(self._activator_args)
        self._files_to_remove = []

    def spawn(self, prefix: Path) -> int:
        """
        Creates a new shell session with the conda environment at `path`
        already activated and waits for the shell session to finish.

        Returns the exit code of such process.
        """
        raise NotImplementedError

    def script(self) -> str:
        raise NotImplementedError

    def prompt(self) -> str:
        raise NotImplementedError

    def prompt_modifier(self) -> str:
        conda_default_env = self._activator._default_env(self._prefix_str)
        return self._activator._prompt_modifier(self._prefix_str, conda_default_env)

    def executable(self) -> str:
        raise NotImplementedError

    def args(self) -> tuple[str, ...]:
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["CONDA_SPAWN"] = "1"
        return env

    def __del__(self):
        for path in self._files_to_remove:
            try:
                os.unlink(path)
            except OSError as exc:
                log.debug("Could not delete %s", path, exc_info=exc)


class PosixShell(Shell):
    Activator = activate.PosixActivator
    default_shell = "/bin/sh"
    default_args = ("-l", "-i")

    def spawn(self, command: Iterable[str] | None = None) -> int:
        return self.spawn_tty(command).wait()

    def script(self) -> str:
        script = self._activator.execute()
        lines = []
        for line in script.splitlines(keepends=True):
            if "PS1=" in line:
                continue
            lines.append(line)
        return "".join(lines)

    def prompt(self) -> str:
        return f'PS1="{self.prompt_modifier()}${{PS1:-}}"'

    def executable(self):
        return os.environ.get("SHELL", self.default_shell)

    def args(self):
        return self.default_args

    # Sentinel printed after activation to reliably detect when the
    # spawned shell is ready.  Everything before this marker (including
    # any initial prompt rendered with stale env vars) is consumed
    # before ``interact()`` starts, preventing a duplicate prompt.
    _READY_MARKER = "__CONDA_SPAWN_READY__"

    def spawn_tty(self, command: Iterable[str] | None = None) -> pexpect.spawn:
        def _sigwinch_passthrough(sig, data):
            # NOTE: Taken verbatim from pexpect's .interact() docstring.
            # Check for buggy platforms (see pexpect.setwinsize()).
            if "TIOCGWINSZ" in dir(termios):
                TIOCGWINSZ = termios.TIOCGWINSZ
            else:
                TIOCGWINSZ = 1074295912  # assume
            s = struct.pack("HHHH", 0, 0, 0, 0)
            a = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), TIOCGWINSZ, s))
            child.setwinsize(a[0], a[1])

        size = shutil.get_terminal_size()

        child = pexpect.spawn(
            self.executable(),
            [*self.args()],
            env=self.env(),
            echo=False,
            dimensions=(size.lines, size.columns),
        )
        try:
            with NamedTemporaryFile(
                prefix="conda-spawn-",
                suffix=self.Activator.script_extension,
                delete=False,
                mode="w",
            ) as f:
                f.write(self.script())
            signal.signal(signal.SIGWINCH, _sigwinch_passthrough)
            # Source the activation script, set the prompt, re-enable echo,
            # then print a ready marker.  Using printf (no trailing newline)
            # lets expect_exact consume everything up to and including the
            # marker without leaving stray characters in the buffer.
            child.sendline(
                f' . "{f.name}" && {self.prompt()} && stty echo'
                f" && printf {self._READY_MARKER}"
            )
            child.expect_exact(self._READY_MARKER)
            if command:
                child.sendline(shlex.join(command))
            if sys.stdin.isatty():
                child.interact()
            return child
        finally:
            self._files_to_remove.append(f.name)


class BashShell(PosixShell):
    def executable(self):
        return "bash"


class ZshShell(PosixShell):
    def executable(self):
        return "zsh"


class CshShell(Shell):
    pass


class XonshShell(Shell):
    pass


class FishShell(Shell):
    pass


class PowershellShell(Shell):
    Activator = activate.PowerShellActivator

    def spawn_popen(
        self, command: Iterable[str] | None = None, **kwargs
    ) -> subprocess.Popen:
        try:
            with NamedTemporaryFile(
                prefix="conda-spawn-",
                suffix=self.Activator.script_extension,
                delete=False,
                mode="w",
            ) as f:
                f.write(f"{self.script()}\r\n")
                f.write(f"{self.prompt()}\r\n")
                if command:
                    command = subprocess.list2cmdline(command)
                    f.write(f"echo {command}\r\n")
                    f.write(f"{command}\r\n")
            return subprocess.Popen(
                [self.executable(), *self.args(), f.name], env=self.env(), **kwargs
            )
        finally:
            self._files_to_remove.append(f.name)

    def spawn(self, command: Iterable[str] | None = None) -> int:
        proc = self.spawn_popen(command)
        proc.communicate()
        return proc.wait()

    def script(self) -> str:
        return self._activator.execute()

    def prompt(self) -> str:
        return (
            "\r\n$old_prompt = $function:prompt\r\n"
            f'function prompt {{"{self.prompt_modifier()}$($old_prompt.Invoke())"}};'
        )

    def executable(self) -> str:
        return "powershell"

    def args(self) -> tuple[str, ...]:
        return ("-NoLogo", "-NoExit", "-File")

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["CONDA_SPAWN"] = "1"
        return env


class CmdExeShell(PowershellShell):
    Activator = activate.CmdExeActivator

    def script(self):
        return "\r\n".join(
            [
                "@ECHO OFF",
                Path(self._activator.execute()).read_text(),
                "@ECHO ON",
            ]
        )

    def prompt(self) -> str:
        return f'@SET "PROMPT={self.prompt_modifier()}$P$G"'

    def executable(self) -> str:
        return "cmd"

    def args(self) -> tuple[str, ...]:
        return ("/D", "/K")


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
    "tcsh": CshShell,
    "xonsh": XonshShell,
    "zsh": ZshShell,
}


def default_shell_class():
    if sys.platform == "win32":
        return CmdExeShell
    return PosixShell


def detect_shell_class():
    try:
        name, _ = shellingham.detect_shell()
    except shellingham.ShellDetectionFailure:
        return default_shell_class()
    else:
        try:
            return SHELLS[name]
        except KeyError:
            log.warning("Did not recognize shell %s, returning default.", name)
            return default_shell_class()
