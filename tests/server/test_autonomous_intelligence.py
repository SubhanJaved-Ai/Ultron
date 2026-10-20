import pytest

from openjarvis.core.user_preferences import set_user_address
from openjarvis.server.autonomous_intelligence import generate_autonomous_response


@pytest.fixture(autouse=True)
def _setup_address(tmp_path, monkeypatch):
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
    set_user_address("sir")


def test_autonomous_greeting():
    resp = generate_autonomous_response("Hello Jarvis")
    assert "sir" in resp.lower()
    assert (
        "directive" in resp.lower()
        or "ready" in resp.lower()
        or "command" in resp.lower()
    )


def test_autonomous_identity():
    resp = generate_autonomous_response("Who are you?")
    assert "JARVIS" in resp


def test_autonomous_math():
    resp = generate_autonomous_response("What is 50 * 4?")
    assert "200" in resp
    assert "sir" in resp.lower()


def test_autonomous_time():
    resp = generate_autonomous_response("What time is it?")
    assert "current time" in resp.lower()
    assert "sir" in resp.lower()


def test_autonomous_knowledge():
    resp = generate_autonomous_response("What is quantum computing?")
    assert "quantum" in resp.lower()
    assert "sir" in resp.lower()
