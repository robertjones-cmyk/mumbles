import pytest

from mumbles import inject
from mumbles.inject import InjectError, deliver


@pytest.fixture
def clipboard(monkeypatch):
    """A fake pasteboard plus a log of the keystrokes we would have sent."""
    state = {"content": "PREVIOUS", "pastes": 0, "typed": []}
    monkeypatch.setattr(inject, "get_clipboard", lambda: state["content"])
    monkeypatch.setattr(inject, "set_clipboard",
                        lambda text: state.__setitem__("content", text))
    monkeypatch.setattr(inject, "send_paste",
                        lambda: state.__setitem__("pastes", state["pastes"] + 1))
    monkeypatch.setattr(inject, "type_text",
                        lambda text, delay=0.0: state["typed"].append(text))
    return state


def test_paste_then_restore_the_previous_clipboard(clipboard):
    assert deliver("hello", restore_delay=0.0) == "pasted"
    assert clipboard["pastes"] == 1
    assert clipboard["content"] == "PREVIOUS"


def test_clipboard_only_mode_leaves_the_text_on_the_pasteboard(clipboard):
    assert deliver("hello", auto_paste=False) == "clipboard"
    assert clipboard["pastes"] == 0
    assert clipboard["content"] == "hello"


def test_restore_can_be_disabled(clipboard):
    assert deliver("hello", restore_clipboard=False, restore_delay=0.0) == "pasted"
    assert clipboard["content"] == "hello"


def test_falls_back_to_typing_when_paste_is_blocked(clipboard, monkeypatch):
    monkeypatch.setattr(inject, "send_paste",
                        lambda: (_ for _ in ()).throw(InjectError("no accessibility")))
    assert deliver("hello", restore_delay=0.0) == "typed"
    assert clipboard["typed"] == ["hello"]


def test_gives_up_to_the_clipboard_when_typing_also_fails(clipboard, monkeypatch):
    monkeypatch.setattr(inject, "send_paste",
                        lambda: (_ for _ in ()).throw(InjectError("nope")))
    monkeypatch.setattr(inject, "type_text",
                        lambda text, delay=0.0: (_ for _ in ()).throw(InjectError("nope")))
    assert deliver("hello", restore_delay=0.0) == "clipboard"
    assert clipboard["content"] == "hello"   # text is never lost


def test_empty_text_is_a_no_op(clipboard):
    assert deliver("") == "clipboard"
    assert clipboard["content"] == "PREVIOUS"
    assert clipboard["pastes"] == 0
