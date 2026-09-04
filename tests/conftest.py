import pytest


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point config, history and recordings at a throwaway directory."""
    monkeypatch.setenv("MUMBLES_HOME", str(tmp_path))
    return tmp_path
