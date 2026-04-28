import sys

import pytest
import shellingham

from conda_spawn.contrib import (
    CshShell,
    FishShell,
    TcshShell,
    XonshShell,
)
from conda_spawn.registry import (
    SHELLS,
    default_shell_class,
    detect_shell_class,
)
from conda_spawn.shell import (
    BashShell,
    CmdExeShell,
    PosixShell,
    ZshShell,
)


def test_default_shell_class():
    expected = CmdExeShell if sys.platform == "win32" else PosixShell
    assert default_shell_class() is expected


def test_detect_shell_class_fallback_on_failure(monkeypatch):
    """If shellingham fails, detect_shell_class falls back to the default."""

    def _raise(*args, **kwargs):
        raise shellingham.ShellDetectionFailure("no shell")

    monkeypatch.setattr(shellingham, "detect_shell", _raise)
    assert detect_shell_class() is default_shell_class()


def test_detect_shell_class_unknown_returns_default(monkeypatch):
    """Unknown shell names fall back to the default class with a warning."""
    monkeypatch.setattr(shellingham, "detect_shell", lambda: ("not-a-real-shell", "/x"))
    assert detect_shell_class() is default_shell_class()


@pytest.mark.parametrize(
    "shell_name, expected_cls",
    [
        ("bash", BashShell),
        ("zsh", ZshShell),
        ("fish", FishShell),
        ("csh", CshShell),
        ("tcsh", TcshShell),
        ("xonsh", XonshShell),
    ],
)
def test_detect_shell_class_known(monkeypatch, shell_name, expected_cls):
    monkeypatch.setattr(
        shellingham,
        "detect_shell",
        lambda: (shell_name, f"/bin/{shell_name}"),
    )
    assert detect_shell_class() is expected_cls


@pytest.mark.parametrize(
    "name",
    [
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
    ],
)
def test_shells_registry_covers_supported_name(name):
    """The SHELLS dispatch table must include every shell we claim to support."""
    assert name in SHELLS
