import threading

import pexpect
import pyte
import pytest


pytest_plugins = ("conda.testing.fixtures",)


@pytest.fixture(scope="session")
def simple_env(session_tmp_env):
    with session_tmp_env() as prefix:
        yield prefix


@pytest.fixture
def vt100_terminal():
    """Spawn a command in a PTY with a pyte VT100 emulator attached.

    pexpect alone can't test xonsh: its readline backend sends a cursor
    position query (\\x1b[6n]) and blocks until the terminal responds.
    pexpect doesn't emulate terminal responses, so xonsh hangs forever.
    This fixture pairs pexpect with pyte, which processes the escape
    sequences and maintains a virtual screen we can assert on.
    """
    procs = []

    def _spawn(command, args, env, cols=200, rows=30):
        screen = pyte.Screen(cols, rows)
        stream = pyte.Stream(screen)
        proc = pexpect.spawn(
            command,
            args,
            env={**env, "TERM": "xterm"},
            dimensions=(rows, cols),
        )

        stop = threading.Event()

        def _feed():
            while not stop.is_set():
                try:
                    data = proc.read_nonblocking(4096, timeout=0.1)
                    stream.feed(data.decode(errors="replace"))
                except pexpect.TIMEOUT:
                    continue
                except pexpect.EOF:
                    break

        reader = threading.Thread(target=_feed, daemon=True)
        reader.start()
        procs.append((proc, stop, reader))
        return screen

    yield _spawn

    for proc, stop, reader in procs:
        stop.set()
        proc.sendline("exit")
        proc.close(force=True)
        reader.join(timeout=5)
