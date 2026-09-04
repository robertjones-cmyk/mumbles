import pytest

from mumbles.hotkey import (HotkeyError, HotkeyListener, format_combo,
                            parse_combo, pretty_combo)


def test_parse_normalises_brackets_and_aliases():
    assert parse_combo("<cmd>+<shift>+space") == ["cmd", "shift", "space"]
    assert parse_combo("Command+Option+D") == ["cmd", "alt", "d"]
    assert parse_combo("<ctrl>+ALT+escape") == ["ctrl", "alt", "esc"]


def test_parse_deduplicates_and_rejects_junk():
    assert parse_combo("cmd+cmd+a") == ["cmd", "a"]
    for bad in ("", "   ", "cmd+", "+a"):
        with pytest.raises(HotkeyError):
            parse_combo(bad)


def test_format_and_pretty():
    assert format_combo(["cmd", "shift", "a"]) == "<cmd>+<shift>+a"
    assert pretty_combo(["cmd", "shift", "space"]) == "⌘⇧Space"


def _listener(activation, events):
    return HotkeyListener(
        "<cmd>+<shift>+space",
        activation,
        on_activate=lambda: events.append("start"),
        on_deactivate=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"),
    )


def _press(listener, *tokens):
    for token in tokens:
        listener._handle_press(token)


def _release(listener, *tokens):
    for token in tokens:
        listener._handle_release(token)


def test_hold_fires_on_full_combo_and_stops_on_release():
    events = []
    listener = _listener("hold", events)
    _press(listener, "cmd", "shift")
    assert events == []          # partial combo does nothing
    _press(listener, "space")
    assert events == ["start"]
    _release(listener, "space")
    assert events == ["start", "stop"]
    _release(listener, "cmd", "shift")
    assert events == ["start", "stop"]


def test_hold_ignores_key_repeat():
    events = []
    listener = _listener("hold", events)
    _press(listener, "cmd", "shift", "space", "space", "space")
    assert events == ["start"]


def test_toggle_alternates():
    events = []
    listener = _listener("toggle", events)
    for _ in range(2):
        _press(listener, "cmd", "shift", "space")
        _release(listener, "space", "shift", "cmd")
    assert events == ["start", "stop"]
    assert listener.active is False


def test_escape_cancels_an_active_take():
    events = []
    listener = _listener("toggle", events)
    _press(listener, "cmd", "shift", "space")
    _release(listener, "space", "shift", "cmd")
    assert events == ["start"]
    listener._handle_press("esc")
    assert events == ["start", "cancel"]
    assert listener.active is False


def test_escape_is_ignored_when_idle():
    events = []
    listener = _listener("hold", events)
    listener._handle_press("esc")
    assert events == []
