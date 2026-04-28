import pytest


pytest_plugins = ("conda.testing.fixtures",)


@pytest.fixture(scope="session")
def simple_env(session_tmp_env):
    with session_tmp_env() as prefix:
        yield prefix
