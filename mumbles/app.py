"""The dictation engine: hotkey -> record -> transcribe -> insert.

`DictationApp` owns the state machine and runs transcription on a worker
thread, so holding the hotkey never blocks the keyboard listener.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional

from . import audio, inject, llm, paths, postprocess, sounds
from .config import Config
from .history import History
from .hotkey import HotkeyListener, parse_combo, pretty_combo
from .transcribe import Engine, Transcript, build_engine

IDLE = "idle"
RECORDING = "recording"
TRANSCRIBING = "transcribing"


class DictationApp:
    """Wire the pieces together. UI-agnostic: the menu bar and the headless
    daemon both drive this same object."""

    def __init__(
        self,
        cfg: Config,
        on_state: Optional[Callable[[str], None]] = None,
        on_result: Optional[Callable[[str, Transcript], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.cfg = cfg
        self.state = IDLE
        self.on_state = on_state or (lambda state: None)
        self.on_result = on_result or (lambda text, transcript: None)
        self.on_error = on_error or (lambda exc: None)
        self.recorder = audio.Recorder(
            sample_rate=cfg.sample_rate,
            device=cfg.input_device,
            max_seconds=cfg.max_recording_seconds,
            on_level=on_level,
        )
        self.history = History(limit=cfg.history_limit)
        self.engine: Optional[Engine] = None
        self.listener: Optional[HotkeyListener] = None
        self.last_text = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def hotkey_label(self) -> str:
        return pretty_combo(parse_combo(self.cfg.hotkey))

    def _set_state(self, state: str) -> None:
        self.state = state
        try:
            self.on_state(state)
        except Exception:
            pass

    def _fail(self, exc: Exception) -> None:
        sounds.play("error", self.cfg.sounds)
        self._set_state(IDLE)
        try:
            self.on_error(exc)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def warm_up(self) -> None:
        """Load the model now so the first dictation isn't the slow one."""
        if self.engine is None:
            self.engine = build_engine(self.cfg)
        self.engine.load()

    def start_recording(self) -> None:
        with self._lock:
            if self.state != IDLE:
                return
            self.state = RECORDING
        try:
            self.recorder.start()
        except audio.AudioError as exc:
            self._fail(exc)
            return
        sounds.play("start", self.cfg.sounds)
        self._set_state(RECORDING)

    def stop_recording(self) -> None:
        """Stop capture and kick transcription off on a worker thread."""
        with self._lock:
            if self.state != RECORDING:
                return
            self.state = TRANSCRIBING
        samples = self.recorder.stop()
        sounds.play("stop", self.cfg.sounds)

        seconds = audio.duration_seconds(samples, self.cfg.sample_rate)
        if seconds < self.cfg.min_recording_seconds:
            # A stray tap of the hotkey, not a dictation.
            self._set_state(IDLE)
            return

        self._set_state(TRANSCRIBING)
        threading.Thread(
            target=self._transcribe_and_deliver,
            args=(samples, seconds),
            daemon=True,
        ).start()

    def cancel(self) -> None:
        """Abandon the current take without transcribing it."""
        with self._lock:
            if self.state != RECORDING:
                return
            self.state = IDLE
        self.recorder.cancel()
        sounds.play("cancel", self.cfg.sounds)
        self._set_state(IDLE)

    def toggle(self) -> None:
        if self.state == RECORDING:
            self.stop_recording()
        elif self.state == IDLE:
            self.start_recording()

    # ------------------------------------------------------------------
    def process(self, samples, seconds: float) -> tuple[str, Transcript]:
        """Audio in, finished text out. No side effects beyond model loading."""
        if self.engine is None:
            self.engine = build_engine(self.cfg)
        transcript = self.engine.transcribe(samples, self.cfg.sample_rate)
        transcript.duration = seconds

        mode = self.cfg.mode()
        text = postprocess.clean(
            transcript.text,
            replacements=self.cfg.replacements,
            drop_fillers=mode.remove_fillers,
        )
        if text and mode.uses_llm:
            try:
                text = llm.rewrite(text, mode, self.cfg).strip()
            except llm.LLMError as exc:
                # Never lose a transcript to a network hiccup: fall back to
                # the locally cleaned text and tell the user why.
                self.on_error(exc)
        return text, transcript

    def _transcribe_and_deliver(self, samples, seconds: float) -> None:
        started = time.monotonic()
        try:
            if self.cfg.keep_recordings:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                audio.write_wav(samples, self.cfg.sample_rate,
                                paths.recordings_dir() / f"{stamp}.wav")
            text, transcript = self.process(samples, seconds)
        except Exception as exc:
            self._fail(exc)
            return

        if not postprocess.is_meaningful(text):
            self._set_state(IDLE)
            return

        payload = text + (" " if self.cfg.trailing_space else "")
        try:
            inject.deliver(
                payload,
                auto_paste=self.cfg.auto_paste,
                restore_clipboard=self.cfg.restore_clipboard,
            )
        except inject.InjectError as exc:
            self.on_error(exc)

        self.last_text = text
        elapsed = time.monotonic() - started
        try:
            self.history.add(
                text=text,
                raw_text=transcript.text,
                mode=self.cfg.active_mode,
                engine=transcript.engine,
                model=transcript.model,
                audio_secs=seconds,
                proc_secs=elapsed,
            )
        except Exception:
            pass  # history is a nicety, never a blocker

        sounds.play("done", self.cfg.sounds)
        self._set_state(IDLE)
        try:
            self.on_result(text, transcript)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def bind_hotkey(self) -> HotkeyListener:
        """Install the global hotkey listener for the configured activation."""
        listener = HotkeyListener(
            self.cfg.hotkey,
            "toggle" if self.cfg.activation == "toggle" else "hold",
            on_activate=self.start_recording,
            on_deactivate=self.stop_recording,
            on_cancel=self.cancel,
        )
        listener.start()
        self.listener = listener
        return listener

    def set_mode(self, name: str) -> None:
        self.cfg.active_mode = name
        self.cfg.save()

    def shutdown(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        if self.recorder.recording:
            self.recorder.cancel()
