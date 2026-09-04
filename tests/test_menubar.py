"""Menu bar pump tests, driven through a stand-in for rumps.

These run anywhere: the fake records what would have been drawn instead of
talking to AppKit.
"""

import sys
import types

import pytest

from mumbles.app import IDLE, RECORDING, TRANSCRIBING
from mumbles.config import Config
from mumbles.meter import LEVELS


class FakeMenuItem:
    def __init__(self, title, callback=None):
        self.title = title
        self.callback = callback
        self.children = []

    def add(self, item):
        self.children.append(item)

    def clear(self):
        self.children = []


class FakeApp:
    def __init__(self, name, title=None, quit_button=None):
        self.name = name
        self.title = title
        self.menu = []
        self.title_history = []

    def __setattr__(self, key, value):
        if key == "title" and "title_history" in self.__dict__:
            self.__dict__["title_history"].append(value)
        super().__setattr__(key, value)

    def run(self):
        raise AssertionError("run() must not be called in tests")


class FakeTimer:
    def __init__(self, callback, interval):
        self.callback = callback
        self.interval = interval
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


@pytest.fixture
def fake_rumps(monkeypatch):
    module = types.ModuleType("rumps")
    module.App = FakeApp
    module.MenuItem = FakeMenuItem
    module.Timer = FakeTimer
    module.notifications = []
    module.notification = lambda title, subtitle, message: \
        module.notifications.append((title, subtitle, message))
    module.alert = lambda **kwargs: None
    module.quit_application = lambda: None
    monkeypatch.setitem(sys.modules, "rumps", module)
    return module


@pytest.fixture
def bar(fake_rumps, sandbox):
    from mumbles.menubar import MenuBarApp

    return MenuBarApp(Config())


def test_idle_bar_shows_just_the_glyph(bar):
    bar._tick()
    assert bar.app.title == "🎙"
    assert bar.toggle_item.title == "Start dictation"


def test_recording_bar_shows_a_meter(bar):
    bar._on_state(RECORDING)
    bar._tick()
    assert bar.app.title.startswith("🔴 ")
    assert bar.app.title.endswith(LEVELS[0] * 6)      # silence, so a flat bar
    assert bar.toggle_item.title == "Stop dictation"


def test_the_meter_tracks_incoming_audio_levels(bar):
    bar._on_state(RECORDING)
    bar._tick()
    quiet = bar.app.title

    bar.meter.push(0.3)                                # someone starts talking
    bar._tick()
    loud = bar.app.title

    assert loud != quiet
    assert LEVELS[-1] in loud
    assert bar.meter.level > 0.5


def test_the_meter_falls_back_to_rest_after_recording_stops(bar):
    bar._on_state(RECORDING)
    bar.meter.push(0.3)
    bar._tick()
    bar._on_state(IDLE)
    for _ in range(20):
        bar._tick()
    assert bar.meter.level == 0.0
    assert bar.app.title == "🎙"


def test_transcribing_state_has_its_own_glyph(bar):
    bar._on_state(TRANSCRIBING)
    bar._tick()
    assert bar.app.title == "✍️"


def test_the_title_is_only_redrawn_when_it_changes(bar):
    bar._tick()
    drawn = len(bar.app.title_history)
    for _ in range(10):
        bar._tick()
    assert len(bar.app.title_history) == drawn


def test_levels_pushed_from_the_audio_thread_reach_the_meter(bar):
    # This is the wiring the recorder uses: DictationApp -> Recorder.on_level.
    bar.dictation.recorder.on_level(0.3)
    bar._on_state(RECORDING)
    bar._tick()
    assert bar.meter.level > 0.5


def test_background_threads_never_draw_directly(bar):
    """State callbacks must only set attributes; drawing waits for the tick."""
    bar._tick()
    before = list(bar.app.title_history)
    bar._on_state(RECORDING)
    bar._on_result("hi", None)
    bar._on_error(RuntimeError("boom"))
    assert bar.app.title_history == before
    bar._tick()
    assert bar.app.title_history != before


def test_errors_surface_as_notifications_on_the_tick(bar, fake_rumps):
    bar._on_error(RuntimeError("no microphone"))
    assert fake_rumps.notifications == []
    bar._tick()
    assert fake_rumps.notifications[0][2] == "no microphone"
    bar._tick()
    assert len(fake_rumps.notifications) == 1      # drained, not repeated


def test_history_menu_refreshes_after_a_result(bar):
    bar._tick()
    assert bar.history_menu.children[0].title == "(nothing yet)"
    bar.dictation.history.add("buy more coffee")
    bar._on_result("buy more coffee", None)
    bar._tick()
    assert bar.history_menu.children[0].title == "buy more coffee"


def test_long_history_entries_are_truncated(bar):
    bar.dictation.history.add("x" * 200)
    bar._on_result("x" * 200, None)
    bar._tick()
    assert len(bar.history_menu.children[0].title) == 46


def test_mode_menu_marks_the_active_mode(bar):
    titles = [child.title for child in bar.mode_menu.children]
    assert any(title.startswith("✓ ") and "clean" in title for title in titles)


def test_status_line_matches_the_activation_style(fake_rumps, sandbox):
    from mumbles.menubar import MenuBarApp

    assert "Hold" in MenuBarApp(Config(activation="hold")).status_item.title
    assert "Tap" in MenuBarApp(Config(activation="toggle")).status_item.title
