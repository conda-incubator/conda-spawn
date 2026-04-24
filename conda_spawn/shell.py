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


class UnixTTYShell(Shell):
    """
    Common base for Unix-like shells that ``conda spawn`` drives through a
    pseudo-terminal with ``pexpect``.  Subclasses provide the per-shell
    bits: ``Activator``, how to source a file, how to set the prompt, how
    to print the ready marker, and what to strip from the activator's own
    prompt output.
    """

    default_shell: str = "/bin/sh"
    default_args: tuple[str, ...] = ("-l", "-i")

    # Sentinel printed after activation to reliably detect when the
    # spawned shell is ready.  Everything before this marker (including
    # any initial prompt rendered with stale env vars) is consumed
    # before `interact()` starts, preventing a duplicate prompt.
    _READY_MARKER = "__CONDA_SPAWN_READY__"

    # Substrings that identify prompt-setting lines emitted by the
    # activator; those lines are stripped from ``script()`` because
    # ``prompt()`` installs its own, conda-spawn-friendly prompt.
    _prompt_strip_markers: tuple[str, ...] = ()

    def spawn(self, command: Iterable[str] | None = None) -> int:
        return self.spawn_tty(command).wait()

    def script(self) -> str:
        """Activation script for this shell.

        Mirrors the output of ``conda <shell>.activate`` for this shell
        (stripped of the activator's own prompt handling where needed).
        Used both by the ``conda spawn --hook`` flow and as the base
        content of the temp file sourced by ``spawn_tty``.
        """
        script = self._activator.execute()
        if not self._prompt_strip_markers:
            return script
        lines = [
            line
            for line in script.splitlines(keepends=True)
            if not any(marker in line for marker in self._prompt_strip_markers)
        ]
        return "".join(lines)

    def _spawn_script(self) -> str:
        """
        Full contents of the temp file the spawned shell will source:
        activation + prompt setup + post-activation command + ready
        marker.  Stuffing everything into a single sourced file lets
        multi-line / multi-statement snippets (e.g. fish function defs,
        xonsh Python statements) run without having to fit into one
        ``sendline`` call.
        """
        parts = [self.script()]
        for extra in (
            self.prompt(),
            self._post_activation_command(),
            self._ready_marker_command(),
        ):
            if extra:
                parts.append(extra)
        return "\n".join(p.rstrip("\n") for p in parts) + "\n"

    def prompt(self) -> str:
        raise NotImplementedError

    def executable(self) -> str:
        return os.environ.get("SHELL", self.default_shell)

    def args(self) -> tuple[str, ...]:
        return self.default_args

    @property
    def _script_suffix(self) -> str:
        """File suffix used for the temporary activation script."""
        return self.Activator.script_extension

    def _source_command(self, script_path: str) -> str:
        """Command that sources ``script_path`` in this shell."""
        raise NotImplementedError

    def _post_activation_command(self) -> str:
        """Run after activation; re-enables terminal echo by default."""
        return "stty echo"

    def _ready_marker_command(self) -> str:
        """Print the ready marker with no trailing newline."""
        return f"printf {self._READY_MARKER}"

    def _commandline(self, script_path: str) -> str:
        return self._source_command(script_path)

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
                suffix=self._script_suffix,
                delete=False,
                mode="w",
            ) as f:
                f.write(self._spawn_script())
            signal.signal(signal.SIGWINCH, _sigwinch_passthrough)
            # Source the activation script, set the prompt, re-enable echo,
            # then print a ready marker.  ``expect_exact`` consumes
            # everything up to and including the marker, so any stale
            # initial prompt rendered before activation is discarded.
            child.sendline(self._commandline(f.name))
            child.expect_exact(self._READY_MARKER)
            if command:
                child.sendline(shlex.join(command))
            if sys.stdin.isatty():
                child.interact()
            return child
        finally:
            self._files_to_remove.append(f.name)


class PosixShell(UnixTTYShell):
    Activator = activate.PosixActivator
    default_shell = "/bin/sh"
    _prompt_strip_markers = ("PS1=",)

    def prompt(self) -> str:
        return f'PS1="{self.prompt_modifier()}${{PS1:-}}"'

    def _source_command(self, script_path: str) -> str:
        return f'. "{script_path}"'


class BashShell(PosixShell):
    def executable(self):
        return "bash"


class ZshShell(PosixShell):
    def executable(self):
        return "zsh"


class FishShell(UnixTTYShell):
    Activator = activate.FishActivator
    default_shell = "fish"

    def prompt(self) -> str:
        # Preserve any pre-existing ``fish_prompt`` (including ones installed
        # by prompt tools like starship) and prepend conda's prompt modifier
        # so users see their env name regardless of their shell setup.
        return (
            "if functions -q fish_prompt\n"
            "    if not functions -q __conda_spawn_orig_fish_prompt\n"
            "        functions -c fish_prompt __conda_spawn_orig_fish_prompt\n"
            "        functions -e fish_prompt\n"
            "    end\n"
            "end\n"
            "function fish_prompt\n"
            '    printf "%s" "$CONDA_PROMPT_MODIFIER"\n'
            "    if functions -q __conda_spawn_orig_fish_prompt\n"
            "        __conda_spawn_orig_fish_prompt\n"
            "    end\n"
            "end"
        )

    def _source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def executable(self) -> str:
        return "fish"


class CshShell(UnixTTYShell):
    Activator = activate.CshActivator
    default_shell = "csh"
    default_args = ("-i",)
    _prompt_strip_markers = ("set prompt=",)

    def prompt(self) -> str:
        # csh/tcsh do not define $prompt automatically in all modes; guard
        # against "Undefined variable" by initialising it to "" if absent.
        return (
            'if (! $?prompt) set prompt = ""\n'
            f'set prompt="{self.prompt_modifier()}${{prompt}}"'
        )

    def _source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def _ready_marker_command(self) -> str:
        # csh does not ship a ``printf`` builtin; ``echo -n`` is portable
        # across csh/tcsh on the platforms we support.
        return f'echo -n "{self._READY_MARKER}"'

    def executable(self) -> str:
        return "csh"


class TcshShell(CshShell):
    default_shell = "tcsh"

    def executable(self) -> str:
        return "tcsh"


class XonshShell(UnixTTYShell):
    Activator = activate.XonshActivator
    default_shell = "xonsh"
    default_args = ("-i",)

    @property
    def _script_suffix(self) -> str:
        # The ``XonshActivator`` reports ``.sh`` (for bash-sourced
        # ``activate.d`` scripts) but ``execute()`` emits xonsh syntax.
        # ``.xsh`` is the canonical extension for xonsh scripts.
        return ".xsh"

    def prompt(self) -> str:
        # Prepend ``CONDA_PROMPT_MODIFIER`` to ``$PROMPT`` while keeping
        # any format-field tokens in the user's prompt intact.
        return (
            "$PROMPT = ${...}.get('CONDA_PROMPT_MODIFIER', '') + $PROMPT"
        )

    def _source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def _post_activation_command(self) -> str:
        # In xonsh, bare ``stty echo`` is treated as subprocess but the
        # explicit ``$[...]`` form is unambiguous inside a sourced script.
        return "$[stty echo]"

    def _ready_marker_command(self) -> str:
        return f'print({self._READY_MARKER!r}, end="", flush=True)'

    def executable(self) -> str:
        return "xonsh"


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
        # ``-NoExit`` keeps PowerShell at its prompt after the activation
        # script finishes, which is the whole point of ``conda spawn`` for
        # an interactive user.  Without a TTY on stdin (tests, pipelines)
        # we want PowerShell to exit cleanly once the script is done so the
        # caller's ``communicate()`` returns instead of relying on a stdin-
        # EOF race that can blow past the test's timeout on slow runners.
        if sys.stdin.isatty():
            return ("-NoLogo", "-NoExit", "-File")
        return ("-NoLogo", "-File")

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
    "tcsh": TcshShell,
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
