import sys

import pytest
from subprocess import PIPE, check_output

from conda.base.context import reset_context

from conda_spawn.shell import (
    BashShell,
    CmdExeShell,
    PosixShell,
    PowershellShell,
    UnixShell,
    ZshShell,
)


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

    `spawn_tty()` prints a distinctive ready marker after the activation
    script, the new `PS1`, and `stty echo` have all been applied, and
    then blocks on `expect_exact` until it sees that marker. Because
    `expect_exact` consumes everything up to *and including* the match,
    any output the shell emitted before activation completed -- including
    an initial prompt rendered from the parent process's (stale)
    `CONDA_DEFAULT_ENV`, which is what prompt tools like starship would
    read -- ends up in `child.before` and is never forwarded to the
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


@pytest.mark.parametrize(
    "cls, expected",
    [
        (BashShell, "bash"),
        (ZshShell, "zsh"),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else x,
)
def test_shell_executable(cls, expected, simple_env):
    assert cls(simple_env).executable() == expected


@pytest.mark.parametrize(
    "cls, expected_markers",
    [
        (PosixShell, ("PS1=",)),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else repr(x),
)
def test_prompt_strip_markers(cls, expected_markers):
    """Each subclass must declare the activator lines it wants stripped."""
    assert cls.prompt_strip_markers == expected_markers


def test_unix_shell_is_abstract_enough_to_require_subclass(simple_env):
    """Instantiating UnixShell directly fails on the abstract `Activator`.

    UnixShell deliberately does not pick an Activator; it's the base class
    shared by PosixShell / FishShell / CshShell / XonshShell.
    """
    with pytest.raises(AttributeError):
        UnixShell(simple_env)
