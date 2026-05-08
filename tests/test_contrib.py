import shutil
import sys

import pexpect
import pytest

from conda_spawn.contrib import (
    CshShell,
    FishShell,
    TcshShell,
    XonshShell,
)


@pytest.fixture
def fish_shell(simple_env):
    return FishShell(simple_env)


@pytest.fixture
def xonsh_shell(simple_env):
    return XonshShell(simple_env)


def _read_via_exit(proc, shell_name: str = "exit") -> str:
    """Send `exit` and collect all output until EOF.

    csh/tcsh/xonsh do not exit on a single `sendeof()`, so we send an explicit
    `exit` command and then wait for the process to terminate.
    """
    proc.sendline("exit")
    try:
        proc.expect(pexpect.EOF, timeout=15)
    except pexpect.TIMEOUT:
        proc.terminate(force=True)
    return (proc.before or b"").decode(errors="replace")


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell(simple_env):
    shell = FishShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    proc.sendeof()
    out = proc.read().decode(errors="replace")
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell_ready_marker_synchronization(simple_env):
    """Regression test: FishShell must use the ready-marker sync approach."""
    shell = FishShell(simple_env)
    proc = shell.spawn_tty()
    try:
        marker = FishShell.READY_MARKER
        assert marker, "FishShell must define a non-empty READY_MARKER"
        assert proc.after == marker.encode()
    finally:
        proc.sendeof()
        proc.read()


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("csh") is None, reason="csh not installed")
def test_csh_shell(simple_env):
    shell = CshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    out = _read_via_exit(proc)
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("tcsh") is None, reason="tcsh not installed")
def test_tcsh_shell(simple_env):
    shell = TcshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    out = _read_via_exit(proc)
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("xonsh") is None, reason="xonsh not installed")
def test_xonsh_shell(simple_env):
    shell = XonshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline(
        "import os; print('\\n'.join(f'{k}={v}' for k,v in __xonsh__.env.items()"
        " if k.startswith('CONDA_')))"
    )
    out = _read_via_exit(proc)
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.parametrize(
    "cls, expected",
    [
        (FishShell, "fish"),
        (CshShell, "csh"),
        (TcshShell, "tcsh"),
        (XonshShell, "xonsh"),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else x,
)
def test_shell_executable(cls, expected, simple_env):
    assert cls(simple_env).executable() == expected


def test_fish_shell_prompt_preserves_existing_prompt(fish_shell):
    prompt = fish_shell.prompt()
    # Copies any existing fish_prompt to a namespaced backup ...
    assert "__conda_spawn_orig_fish_prompt" in prompt
    # ... and prepends CONDA_PROMPT_MODIFIER to the new fish_prompt.
    assert '"$CONDA_PROMPT_MODIFIER"' in prompt


def test_fish_shell_source_command_and_suffix(fish_shell):
    assert fish_shell.source_command("/tmp/x.fish") == 'source "/tmp/x.fish"'
    assert fish_shell.script_suffix == ".fish"


@pytest.mark.parametrize("cls", [CshShell, TcshShell], ids=lambda c: c.__name__)
def test_csh_family_prompt_guards_undefined_prompt(cls, simple_env):
    """Regression test: csh raises 'Undefined variable' without this guard."""
    prompt = cls(simple_env).prompt()
    assert 'if (! $?prompt) set prompt = ""' in prompt
    assert "set prompt=" in prompt
    # The guard must come before the assignment, otherwise the expansion
    # in ${prompt} happens before $prompt has been initialised.
    assert prompt.index("if (! $?prompt)") < prompt.index("set prompt=")


@pytest.mark.parametrize("cls", [CshShell, TcshShell], ids=lambda c: c.__name__)
def test_csh_family_ready_marker_uses_echo(cls, simple_env):
    """csh has no printf builtin; echo -n is the portable alternative."""
    assert cls(simple_env).ready_marker_command().startswith("echo -n ")


def test_xonsh_shell_rewrites_del_var(xonsh_shell):
    """Regression test: bare `del $VAR` raises KeyError on fresh shells.

    The XonshShell.script() override must replace every such line with the
    safe `${...}.pop("VAR", None)` form.
    """
    script = xonsh_shell.script()
    assert "del $" not in script
    # The activator always emits these unset lines; each should be
    # rewritten. Checking one representative confirms the regex works.
    assert '${...}.pop("CONDA_EXE", None)' in script


def test_xonsh_shell_script_suffix_is_xsh(xonsh_shell):
    """The activator reports .sh but xonsh needs .xsh for correct parsing."""
    assert xonsh_shell.script_suffix == ".xsh"


def test_xonsh_shell_post_activation_uses_subproc_form(xonsh_shell):
    """Bare `stty echo` is ambiguous in xonsh; `$[...]` forces subproc."""
    assert xonsh_shell.post_activation_command() == "$[stty echo]"


def test_xonsh_shell_ready_marker_uses_print(xonsh_shell):
    cmd = xonsh_shell.ready_marker_command()
    assert cmd.startswith("print(")
    assert "flush=True" in cmd
    assert "end=" in cmd


@pytest.mark.parametrize(
    "cls, expected_markers",
    [
        (CshShell, ("set prompt=",)),
        (TcshShell, ("set prompt=",)),
        (FishShell, ()),
        (XonshShell, ()),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else repr(x),
)
def test_prompt_strip_markers(cls, expected_markers):
    """Each subclass must declare the activator lines it wants stripped."""
    assert cls.prompt_strip_markers == expected_markers
