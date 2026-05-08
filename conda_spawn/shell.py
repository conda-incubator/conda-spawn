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
from typing import ClassVar, Iterable

if sys.platform != "win32":
    import fcntl
    import termios

    import pexpect

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
        # `__init__` may have failed before `_files_to_remove` was set
        # (e.g. if a subclass forgot to declare `Activator`).  Guard
        # against that so the interpreter does not emit a spurious
        # AttributeError during garbage collection.
        for path in getattr(self, "_files_to_remove", ()):
            try:
                os.unlink(path)
            except OSError as exc:
                log.debug("Could not delete %s", path, exc_info=exc)


class UnixShell(Shell):
    """
    Common base for Unix-like shells that `conda spawn` drives through a
    pseudo-terminal with `pexpect`.  Subclasses provide the per-shell
    bits: `Activator`, how to source a file, how to set the prompt, how
    to print the ready marker, and what to strip from the activator's own
    prompt output.
    """

    default_shell: str = "/bin/sh"
    default_args: tuple[str, ...] = ("-l", "-i")
    # When True, the shell supports passing the activation script via
    # a command-line flag (e.g. bash --rcfile, xonsh --rc) instead of
    # a separate sendline after startup.  This eliminates a PTY
    # round-trip and avoids race conditions with shells that discard
    # typeahead input (like xonsh's readline backend).
    supports_init_injection: ClassVar[bool] = False

    # Sentinel printed after activation to reliably detect when the
    # spawned shell is ready.  Everything before this marker (including
    # any initial prompt rendered with stale env vars) is consumed
    # before `interact()` starts, preventing a duplicate prompt.
    READY_MARKER = "__CONDA_SPAWN_READY__"

    # Substrings that identify prompt-setting lines emitted by the
    # activator; those lines are stripped from `script()` because
    # `prompt()` installs its own, conda-spawn-friendly prompt.
    prompt_strip_markers: tuple[str, ...] = ()

    def spawn(self, command: Iterable[str] | None = None) -> int:
        return self.spawn_tty(command).wait()

    def script(self) -> str:
        """Activation script for this shell.

        Mirrors the output of `conda <shell>.activate` for this shell
        (stripped of the activator's own prompt handling where needed).
        Used both by the `conda spawn --hook` flow and as the base
        content of the temp file sourced by `spawn_tty`.
        """
        script = self._activator.execute()
        if not self.prompt_strip_markers:
            return script
        lines = [
            line
            for line in script.splitlines(keepends=True)
            if not any(marker in line for marker in self.prompt_strip_markers)
        ]
        return "".join(lines)

    def spawn_script(self) -> str:
        """
        Full contents of the temp file the spawned shell will source:
        activation + prompt setup + post-activation command + ready
        marker.  Stuffing everything into a single sourced file lets
        multi-line / multi-statement snippets (e.g. fish function defs,
        xonsh Python statements) run without having to fit into one
        `sendline` call.
        """
        parts = []
        preamble = self.user_rc_preamble()
        if preamble:
            parts.append(preamble)
        parts.append(self.script())
        for extra in (
            self.prompt(),
            self.post_activation_command(),
            self.ready_marker_command(),
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
    def script_suffix(self) -> str:
        """File suffix used for the temporary activation script."""
        return self.Activator.script_extension

    def source_command(self, script_path: str) -> str:
        """Command that sources `script_path` in this shell."""
        raise NotImplementedError

    def post_activation_command(self) -> str:
        """Run after activation; re-enables terminal echo by default."""
        return "stty echo"

    def ready_marker_command(self) -> str:
        """Print the ready marker with no trailing newline."""
        return f"printf {self.READY_MARKER}"

    def user_rc_preamble(self) -> str:
        """Preamble sourcing the user's normal rc files.

        Shells that use init injection override this so the activation
        script re-creates the login/interactive startup the user expects.
        """
        return ""

    def write_init_injection(
        self, script_path: str
    ) -> tuple[tuple[str, ...], dict[str, str]] | None:
        """Return extra argv and env for init-injection launch, or None."""
        return None

    def spawn_tty(self, command: Iterable[str] | None = None) -> pexpect.spawn:
        def resize_child(sig, data):
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

        try:
            with NamedTemporaryFile(
                prefix="conda-spawn-",
                suffix=self.script_suffix,
                delete=False,
                mode="w",
            ) as f:
                f.write(self.spawn_script())

            injection = (
                self.write_init_injection(f.name)
                if self.supports_init_injection
                else None
            )

            if injection is not None:
                # Fast path: pass the activation script on the command line
                # (e.g. bash --rcfile script.sh -i).  GNU long options must
                # come before short options for bash to accept them.
                extra_argv, extra_env = injection
                env = self.env()
                env.update(extra_env)
                child = pexpect.spawn(
                    self.executable(),
                    [*extra_argv, *self.args()],
                    env=env,
                    echo=False,
                    dimensions=(size.lines, size.columns),
                )
            else:
                # Fallback: start the shell, then send the source command
                # via sendline.  This requires a second PTY round-trip and
                # can race with shells that flush their input buffer on
                # startup (e.g. xonsh with prompt_toolkit).
                child = pexpect.spawn(
                    self.executable(),
                    [*self.args()],
                    env=self.env(),
                    echo=False,
                    dimensions=(size.lines, size.columns),
                )
                child.sendline(self.source_command(f.name))

            signal.signal(signal.SIGWINCH, resize_child)
            child.expect_exact(self.READY_MARKER)
            if command:
                child.sendline(shlex.join(command))
            if sys.stdin.isatty():
                child.interact()
            return child
        finally:
            self._files_to_remove.append(f.name)


class PosixShell(UnixShell):
    Activator = activate.PosixActivator
    default_shell = "/bin/sh"
    prompt_strip_markers = ("PS1=",)

    def prompt(self) -> str:
        return f'PS1="{self.prompt_modifier()}${{PS1:-}}"'

    def source_command(self, script_path: str) -> str:
        return f'. "{script_path}"'


class BashShell(PosixShell):
    # Drop -l (login): bash ignores --rcfile in login mode.  The
    # user_rc_preamble manually sources the login files instead.
    default_args: tuple[str, ...] = ("-i",)
    supports_init_injection: ClassVar[bool] = True

    def executable(self):
        return "bash"

    def user_rc_preamble(self) -> str:
        # Replicate bash's login-shell startup sequence since --rcfile
        # requires non-login mode.  Sources /etc/profile, then the first
        # of ~/.bash_profile / ~/.bash_login / ~/.profile that exists.
        # ~/.bashrc is deliberately omitted: the profile files source it
        # if the user wants it (most distros' .bash_profile does).
        return (
            "[ -r /etc/profile ] && . /etc/profile\n"
            'for f in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do\n'
            '  if [ -r "$f" ]; then . "$f"; break; fi\n'
            "done"
        )

    def write_init_injection(
        self, script_path: str
    ) -> tuple[tuple[str, ...], dict[str, str]] | None:
        return (("--rcfile", script_path), {})


class ZshShell(PosixShell):
    def executable(self):
        return "zsh"


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
        # `-NoExit` keeps PowerShell at its prompt after the activation
        # script finishes, which is the whole point of `conda spawn` for
        # an interactive user.  Without a TTY on stdin (tests, pipelines)
        # we want PowerShell to exit cleanly once the script is done so the
        # caller's `communicate()` returns instead of relying on a stdin-
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
