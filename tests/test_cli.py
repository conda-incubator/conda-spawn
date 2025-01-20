import sys

from conda import CondaError


def test_cli(monkeypatch, conda_cli):
    monkeypatch.setattr(sys, "argv", ["conda", *sys.argv[1:]])
    out, err, _ = conda_cli("spawn", "-h", raises=SystemExit)
    assert not err
    assert "conda spawn" in out


def test_nesting_disallowed(monkeypatch, conda_cli):
    monkeypatch.setenv("CONDA_SPAWN", "1")
    conda_cli("spawn", "-p", sys.prefix, "--hook", raises=CondaError)


def test_nesting_replace(monkeypatch, conda_cli):
    monkeypatch.setenv("CONDA_SPAWN", "1")
    out, err, rc = conda_cli("spawn", "-p", sys.prefix, "--hook", "--replace")
    assert sys.prefix in out
    assert not err
    assert not rc


def test_nesting_stack(monkeypatch, conda_cli):
    monkeypatch.setenv("CONDA_SPAWN", "1")
    out, err, rc = conda_cli("spawn", "-p", sys.prefix, "--hook", "--stack")
    assert sys.prefix in out
    assert not err
    assert not rc
