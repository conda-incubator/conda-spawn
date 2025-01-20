import sys

import pytest
from subprocess import PIPE, check_output

from conda.base.context import reset_context

from conda_spawn.shell import PosixShell, PowershellShell, CmdExeShell


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
    out, err, rc = conda_cli("spawn", "--hook", "-p", simple_env)
    print(out)
    print(err, file=sys.stderr)
    assert not rc
    assert not err
    assert "CONDA_EXE" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Only tested on Unix")
def test_hooks_integration_posix(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell posix -p '{simple_env}'"
    script = f'eval "$({hook})"\nenv | sort'
    script_path = tmp_path / "script-eval.sh"
    script_path.write_text(script)

    out = check_output(["bash", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_hooks_integration_powershell(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell powershell -p {simple_env}"
    script = f"{hook} | Out-String | Invoke-Expression\r\nls env:"
    script_path = tmp_path / "script-eval.ps1"
    script_path.write_text(script)

    out = check_output(["powershell", "-NoLogo", "-File", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_hooks_integration_cmd(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell cmd -p {simple_env}"
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
