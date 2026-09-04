"""End-to-end pipeline tests with a stand-in speech engine."""

import time

import pytest

from mumbles import inject, llm
from mumbles.app import IDLE, RECORDING, TRANSCRIBING, DictationApp
from mumbles.config import Config
from mumbles.transcribe import Transcript


class FakeEngine:
    """Returns canned text instead of running Whisper."""

    name = "fake"

    def __init__(self, text="um hello the the world", error=None):
        self.text = text
        self.error = error
        self.loaded = False
        self.calls = 0

    def load(self):
        self.loaded = True

    def transcribe(self, samples, sample_rate):
        self.calls += 1
        if self.error:
            raise self.error
        return Transcript(text=self.text, engine="fake", model="fake-model")


@pytest.fixture
def delivered(monkeypatch):
    """Capture what would have been pasted, instead of touching the OS."""
    captured = []
    monkeypatch.setattr(inject, "deliver",
                        lambda text, **kw: captured.append(text) or "pasted")
    return captured


def _app(sandbox, cfg=None, engine=None, **kwargs):
    instance = DictationApp(cfg or Config(), **kwargs)
    instance.engine = engine or FakeEngine()
    return instance


def test_process_cleans_the_transcript(sandbox):
    instance = _app(sandbox)
    text, transcript = instance.process(samples=[], seconds=1.0)
    assert text == "Hello the world"          # fillers and stutters gone
    assert transcript.text == "um hello the the world"   # raw kept for history
    assert transcript.duration == 1.0


def test_raw_mode_keeps_disfluencies(sandbox):
    cfg = Config(active_mode="raw")
    instance = _app(sandbox, cfg)
    text, _ = instance.process(samples=[], seconds=1.0)
    assert text.lower().startswith("um hello")


def test_custom_vocabulary_is_applied(sandbox):
    cfg = Config(replacements={"the world": "the World"})
    instance = _app(sandbox, cfg, engine=FakeEngine("hello the world"))
    text, _ = instance.process(samples=[], seconds=1.0)
    assert text == "Hello the World"


def test_llm_failure_falls_back_to_the_local_transcript(sandbox, monkeypatch):
    errors = []
    cfg = Config(active_mode="polish")
    instance = _app(sandbox, cfg, on_error=errors.append)
    monkeypatch.setattr(
        llm, "rewrite",
        lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("no api key")))
    text, _ = instance.process(samples=[], seconds=1.0)
    assert text == "Hello the world"     # nothing is lost
    assert isinstance(errors[0], llm.LLMError)


def test_llm_mode_uses_the_rewritten_text(sandbox, monkeypatch):
    cfg = Config(active_mode="polish")
    instance = _app(sandbox, cfg)
    monkeypatch.setattr(llm, "rewrite", lambda text, mode, cfg: "Polished.")
    text, _ = instance.process(samples=[], seconds=1.0)
    assert text == "Polished."


def _wait_for_idle(instance, timeout=5.0):
    deadline = time.monotonic() + timeout
    while instance.state != IDLE and time.monotonic() < deadline:
        time.sleep(0.01)
    assert instance.state == IDLE


def test_full_take_delivers_text_and_records_history(sandbox, delivered, monkeypatch):
    states = []
    instance = _app(sandbox, on_state=states.append)
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 16000)

    instance.start_recording()
    assert instance.state == RECORDING
    instance.stop_recording()
    _wait_for_idle(instance)

    assert delivered == ["Hello the world "]        # trailing space by default
    assert RECORDING in states and TRANSCRIBING in states
    entry = instance.history.recent(1)[0]
    assert entry.text == "Hello the world"
    assert entry.raw_text == "um hello the the world"
    assert entry.engine == "fake"


def test_trailing_space_can_be_turned_off(sandbox, delivered, monkeypatch):
    instance = _app(sandbox, Config(trailing_space=False))
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 16000)
    instance.start_recording()
    instance.stop_recording()
    _wait_for_idle(instance)
    assert delivered == ["Hello the world"]


def test_a_stray_tap_is_discarded(sandbox, delivered, monkeypatch):
    instance = _app(sandbox)
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 100)  # ~6ms

    instance.start_recording()
    instance.stop_recording()
    assert instance.state == IDLE
    assert delivered == []
    assert instance.history.recent() == []


def test_silence_is_not_pasted(sandbox, delivered, monkeypatch):
    instance = _app(sandbox, engine=FakeEngine("[BLANK_AUDIO]"))
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 16000)
    instance.start_recording()
    instance.stop_recording()
    _wait_for_idle(instance)
    assert delivered == []


def test_engine_failure_reports_and_returns_to_idle(sandbox, delivered, monkeypatch):
    errors = []
    instance = _app(sandbox, engine=FakeEngine(error=RuntimeError("model exploded")),
                    on_error=errors.append)
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 16000)
    instance.start_recording()
    instance.stop_recording()
    _wait_for_idle(instance)
    assert delivered == []
    assert "model exploded" in str(errors[0])


def test_cancel_throws_the_take_away(sandbox, delivered, monkeypatch):
    instance = _app(sandbox)
    cancelled = []
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "cancel", lambda: cancelled.append(True))

    instance.start_recording()
    instance.cancel()
    assert instance.state == IDLE
    assert cancelled == [True]
    assert delivered == []


def test_start_is_ignored_while_already_recording(sandbox, monkeypatch):
    starts = []
    instance = _app(sandbox)
    monkeypatch.setattr(instance.recorder, "start", lambda: starts.append(True))
    instance.start_recording()
    instance.start_recording()
    assert starts == [True]


def test_stop_is_ignored_when_not_recording(sandbox, delivered):
    instance = _app(sandbox)
    instance.stop_recording()
    assert instance.state == IDLE
    assert delivered == []


def test_toggle_flips_between_states(sandbox, delivered, monkeypatch):
    instance = _app(sandbox)
    monkeypatch.setattr(instance.recorder, "start", lambda: None)
    monkeypatch.setattr(instance.recorder, "stop", lambda: [0.0] * 16000)
    instance.toggle()
    assert instance.state == RECORDING
    instance.toggle()
    _wait_for_idle(instance)
    assert delivered == ["Hello the world "]


def test_set_mode_persists(sandbox):
    from mumbles import config as config_module

    instance = _app(sandbox)
    instance.set_mode("notes")
    assert config_module.load().active_mode == "notes"


def test_hotkey_label_is_human_readable(sandbox):
    assert _app(sandbox, Config(hotkey="<cmd>+<shift>+space")).hotkey_label == "⌘⇧Space"
