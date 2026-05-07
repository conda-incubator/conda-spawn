from __future__ import annotations

import pytest
from conda.common.compat import on_win

from conda_spawn.shell import PowershellShell


@pytest.mark.skipif(
    not on_win, reason="PowerShell conda function only needed on Windows"
)
def test_powershell_script_defines_conda_function(simple_env):
    """PowerShell script must define a conda function routing to conda.exe (#32).

    Without this, conda.bat (in condabin) silently no-ops for
    activate/deactivate in PowerShell. The function ensures conda.exe
    (the Python entry point) handles the command so main_mock_activate
    fires as intended.
    """
    from conda.base.context import context

    conda_exe = context.conda_exe_vars_dict["CONDA_EXE"]
    shell = PowershellShell(simple_env)
    script = shell.script()
    assert f'function conda {{ & "{conda_exe}" @args }}' in script


@pytest.mark.skipif(on_win, reason="conda function should not be injected on Unix")
def test_powershell_script_no_conda_function_on_unix(simple_env):
    """On non-Windows platforms the conda function is not injected."""
    shell = PowershellShell(simple_env)
    script = shell.script()
    assert "function conda" not in script
