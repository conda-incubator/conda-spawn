import shutil
import sys

import pytest
from subprocess import PIPE, check_output

from conda.base.context import reset_context

from conda_spawn.shell import (
    BashShell,
    CmdExeShell,
    CshShell,
    FishShell,
    PosixShell,
    PowershellShell,
    SHELLS,
    TcshShell,
    UnixShell,
    XonshShell,
    ZshShell,
    default_shell_class,
    detect_shell_class,
)


@pytest.fixture(scope="session")
def simple_env(session_tmp_env):
    with session_tmp_env() as prefix:
        yield prefix


@pytest.fixture(scope="session")
def conda_env(session_tmp_env):
    with session_tmp_env("conda") as prefix:
        yield prefix


@pytest.fixture
def no_prompt(monkeypatch):
    monkeypatch.setenv("CONDA_CHANGEPS1", "false")
    reset_context()
    yield


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_posix_shell(simple_env):
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    proc.sendeof()
    out = proc.read().decode()
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_posix_shell_ready_marker_synchronization(simple_env, request):
    """Regression test for the double-prompt fix (#22).

    ``spawn_tty()`` prints a distinctive ready marker after the activation
    script, the new ``PS1``, and ``stty echo`` have all been applied, and
    then blocks on ``expect_exact`` until it sees that marker.  Because
    ``expect_exact`` consumes everything up to *and including* the match,
    any output the shell emitted before activation completed -- including
    an initial prompt rendered from the parent process's (stale)
    ``CONDA_DEFAULT_ENV``, which is what prompt tools like starship would
    read -- ends up in ``child.before`` and is never forwarded to the
    interactive user.

    Refs conda-incubator/conda-workspaces#20.
    """
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()

    def _drain():
        proc.sendeof()
        proc.read()

    request.addfinalizer(_drain)

    marker = PosixShell.READY_MARKER
    assert marker, "PosixShell must define a non-empty READY_MARKER"
    # expect_exact() leaves the matched literal in child.after; if
    # someone removes the marker sync this assertion fails loudly
    # instead of regressing to the old racy os.read()-based approach.
    assert proc.after == marker.encode()


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


def _read_via_exit(proc, shell_name: str = "exit") -> str:
    """Send 'exit' and collect all output until EOF.

    csh/tcsh/xonsh do not exit on a single sendeof(), so we send an explicit
    ``exit`` command and then wait for the process to terminate.
    """
    import pexpect

    proc.sendline("exit")
    try:
        proc.expect(pexpect.EOF, timeout=15)
    except pexpect.TIMEOUT:
        proc.terminate(force=True)
    return (proc.before or b"").decode(errors="replace")


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


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_powershell(simple_env):
    shell = PowershellShell(simple_env)
    with shell.spawn_popen(command=["ls", "env:"], stdout=PIPE, text=True) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert "CONDA_SPAWN" in out
        assert "CONDA_PREFIX" in out
        assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_cmd(simple_env):
    shell = CmdExeShell(simple_env)
    with shell.spawn_popen(command=["@SET"], stdout=PIPE, text=True) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert "CONDA_SPAWN" in out
        assert "CONDA_PREFIX" in out
        assert str(simple_env) in out


def test_hooks(conda_cli, simple_env):
    out, err, rc = conda_cli("spawn", "--hook", simple_env)
    print(out)
    print(err, file=sys.stderr)
    assert not rc
    assert not err
    assert "CONDA_EXE" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Only tested on Unix")
def test_hooks_integration_posix(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell posix '{simple_env}'"
    script = f'eval "$({hook})"\nenv | sort'
    script_path = tmp_path / "script-eval.sh"
    script_path.write_text(script)

    out = check_output(["bash", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_hooks_integration_powershell(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell powershell {simple_env}"
    script = f"{hook} | Out-String | Invoke-Expression\r\nls env:"
    script_path = tmp_path / "script-eval.ps1"
    script_path.write_text(script)

    out = check_output(["powershell", "-NoLogo", "-File", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_hooks_integration_cmd(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell cmd {simple_env}"
    script = f"FOR /F \"tokens=*\" %%g IN ('{hook}') do @CALL %%g\r\nset"
    script_path = tmp_path / "script-eval.bat"
    script_path.write_text(script)

    out = check_output(["cmd", "/D", "/C", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_condabin_first_posix_shell(simple_env, conda_env, no_prompt):
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline('echo "$PATH"')
    proc.sendeof()
    out = proc.read().decode()
    print(out)
    assert sys.prefix in out
    assert str(simple_env) in out
    assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = PosixShell(conda_env)
    proc = shell.spawn_tty()
    proc.sendline("which conda")
    proc.sendeof()
    print(out)
    out = proc.read().decode()
    assert f"{sys.prefix}/condabin/conda" in out
    assert str(conda_env) not in out


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_condabin_first_powershell(simple_env, conda_env, no_prompt):
    shell = PowershellShell(simple_env)
    with shell.spawn_popen(
        command=["echo", "$env:PATH"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert sys.prefix in out
        assert str(simple_env) in out
        assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = PowershellShell(conda_env)
    with shell.spawn_popen(
        command=["where.exe", "conda"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert out.index(f"{sys.prefix}\\condabin\\conda") < out.index(str(conda_env))


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_condabin_first_cmd(simple_env, conda_env, no_prompt):
    shell = CmdExeShell(simple_env)
    with shell.spawn_popen(command=["echo", "%PATH%"], stdout=PIPE, text=True) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert sys.prefix in out
        assert str(simple_env) in out
        assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = CmdExeShell(conda_env)
    with shell.spawn_popen(
        command=["where.exe", "conda"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert out.index(f"{sys.prefix}\\condabin\\conda") < out.index(str(conda_env))


# ---------------------------------------------------------------------------
# Unit tests that do not need a real PTY.  These exercise the script /
# prompt generation directly and therefore run on every platform, covering
# code paths that the TTY-based tests skip on Windows.
# ---------------------------------------------------------------------------


def test_bash_shell_executable(simple_env):
    assert BashShell(simple_env).executable() == "bash"


def test_zsh_shell_executable(simple_env):
    assert ZshShell(simple_env).executable() == "zsh"


def test_default_shell_class():
    expected = CmdExeShell if sys.platform == "win32" else PosixShell
    assert default_shell_class() is expected


def test_detect_shell_class_fallback_on_failure(monkeypatch):
    """If shellingham fails, detect_shell_class falls back to the default."""
    import shellingham

    from conda_spawn import shell as shell_module

    def _raise(*args, **kwargs):
        raise shellingham.ShellDetectionFailure("no shell")

    monkeypatch.setattr(shell_module.shellingham, "detect_shell", _raise)
    assert detect_shell_class() is default_shell_class()


def test_detect_shell_class_unknown_returns_default(monkeypatch):
    """Unknown shell names fall back to the default class with a warning."""
    from conda_spawn import shell as shell_module

    monkeypatch.setattr(
        shell_module.shellingham, "detect_shell", lambda: ("not-a-real-shell", "/x")
    )
    assert detect_shell_class() is default_shell_class()


def test_detect_shell_class_known(monkeypatch):
    from conda_spawn import shell as shell_module

    monkeypatch.setattr(
        shell_module.shellingham, "detect_shell", lambda: ("bash", "/bin/bash")
    )
    assert detect_shell_class() is BashShell


def test_shells_registry_covers_all_supported_names():
    """The SHELLS dispatch table must include every shell we claim to support."""
    expected = {
        "ash",
        "bash",
        "cmd",
        "cmd.exe",
        "csh",
        "dash",
        "fish",
        "posix",
        "powershell",
        "pwsh",
        "tcsh",
        "xonsh",
        "zsh",
    }
    assert expected <= set(SHELLS)


def test_fish_shell_prompt_preserves_existing_prompt(simple_env):
    prompt = FishShell(simple_env).prompt()
    # Copies any existing fish_prompt to a namespaced backup ...
    assert "__conda_spawn_orig_fish_prompt" in prompt
    # ... and prepends CONDA_PROMPT_MODIFIER to the new fish_prompt.
    assert '"$CONDA_PROMPT_MODIFIER"' in prompt


def test_fish_shell_source_command_and_suffix(simple_env):
    shell = FishShell(simple_env)
    assert shell.source_command("/tmp/x.fish") == 'source "/tmp/x.fish"'
    assert shell.script_suffix == ".fish"


def test_csh_shell_prompt_guards_undefined_prompt(simple_env):
    """Regression test: csh raises 'Undefined variable' without this guard."""
    prompt = CshShell(simple_env).prompt()
    assert 'if (! $?prompt) set prompt = ""' in prompt
    assert "set prompt=" in prompt
    # The guard must come before the assignment, otherwise the expansion
    # in ${prompt} happens before $prompt has been initialised.
    assert prompt.index("if (! $?prompt)") < prompt.index("set prompt=")


def test_csh_shell_ready_marker_uses_echo(simple_env):
    """csh has no printf builtin; echo -n is the portable alternative."""
    assert CshShell(simple_env).ready_marker_command().startswith("echo -n ")


def test_tcsh_shell_inherits_csh_prompt(simple_env):
    # TcshShell is a thin subclass of CshShell and must keep the guard.
    assert 'if (! $?prompt) set prompt = ""' in TcshShell(simple_env).prompt()
    assert TcshShell(simple_env).executable() == "tcsh"


def test_xonsh_shell_rewrites_del_var(simple_env):
    """Regression test: bare `del $VAR` raises KeyError on fresh shells.

    The XonshShell.script() override must replace every such line with the
    safe ``${...}.pop("VAR", None)`` form.
    """
    script = XonshShell(simple_env).script()
    assert "del $" not in script
    # The activator always emits these six unset lines; each should be
    # rewritten.  Checking one representative confirms the regex works.
    assert '${...}.pop("CONDA_EXE", None)' in script


def test_xonsh_shell_script_suffix_is_xsh(simple_env):
    """The activator reports .sh but xonsh needs .xsh for correct parsing."""
    assert XonshShell(simple_env).script_suffix == ".xsh"


def test_xonsh_shell_post_activation_uses_subproc_form(simple_env):
    """Bare ``stty echo`` is ambiguous in xonsh; ``$[...]`` forces subproc."""
    assert XonshShell(simple_env).post_activation_command() == "$[stty echo]"


def test_xonsh_shell_ready_marker_uses_print(simple_env):
    cmd = XonshShell(simple_env).ready_marker_command()
    assert cmd.startswith("print(")
    assert "flush=True" in cmd
    assert "end=" in cmd


def test_unix_shell_base_strips_prompt_markers(simple_env):
    """PosixShell's ``prompt_strip_markers`` removes activator PS1 lines."""
    assert PosixShell.prompt_strip_markers == ("PS1=",)
    assert CshShell.prompt_strip_markers == ("set prompt=",)
    # FishShell / XonshShell do not need stripping.
    assert FishShell.prompt_strip_markers == ()
    assert XonshShell.prompt_strip_markers == ()


def test_unix_shell_is_abstract_enough_to_require_subclass(simple_env):
    """Instantiating UnixShell directly fails on the abstract ``Activator``.

    UnixShell deliberately does not pick an Activator; it's the base class
    shared by PosixShell / FishShell / CshShell / XonshShell.
    """
    with pytest.raises(AttributeError):
        UnixShell(simple_env)
