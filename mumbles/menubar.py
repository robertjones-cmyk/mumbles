"""macOS menu bar UI (requires `rumps`).

The bar item is the whole interface: a live level meter shows the mic is
actually hearing you, and the menu holds mode switching, recent transcripts
and preferences.

Threading note: recording is driven from the hotkey listener's thread and
audio levels arrive on PortAudio's thread, but AppKit must only be touched
from the main thread. So background threads never draw. They set plain
attributes, and a 10 Hz `rumps.Timer` on the main thread reconciles the UI
against them.
"""

from __future__ import annotations

import subprocess
from collections import deque

from . import config as config_module
from . import inject, paths
from .app import IDLE, RECORDING, TRANSCRIBING, DictationApp
from .meter import LevelMeter

GLYPHS = {IDLE: "🎙", RECORDING: "🔴", TRANSCRIBING: "✍️"}

# 10 frames a second: smooth enough to read as live, cheap enough to ignore.
FRAME_INTERVAL = 0.1


def _require_rumps():
    try:
        import rumps
    except ImportError as exc:
        raise SystemExit(
            "the menu bar UI needs rumps. Run: pip install rumps\n"
            "Or run headless instead: mumbles listen"
        ) from exc
    return rumps


class MenuBarApp:
    def __init__(self, cfg) -> None:
        self.rumps = _require_rumps()
        self.cfg = cfg
        self.app = self.rumps.App("mumbles", title=GLYPHS[IDLE], quit_button=None)
        self.meter = LevelMeter()

        # Written by background threads, read by the timer. Plain assignment
        # and deque appends are safe; nothing here needs a lock.
        self._state = IDLE
        self._history_dirty = True
        self._notifications = deque(maxlen=8)
        self._drawn_title = None
        self._drawn_toggle = None

        self.dictation = DictationApp(
            cfg,
            on_state=self._on_state,
            on_result=self._on_result,
            on_error=self._on_error,
            on_level=self.meter.push,
        )
        self._build_menu()

    # --- menu construction ---------------------------------------------
    def _build_menu(self) -> None:
        rumps = self.rumps
        self.toggle_item = rumps.MenuItem("Start dictation", callback=self._toggle)
        self.status_item = rumps.MenuItem(self._idle_hint(), callback=None)

        self.mode_menu = rumps.MenuItem("Mode")
        self._rebuild_modes()

        self.history_menu = rumps.MenuItem("Recent")
        self.history_menu.add(rumps.MenuItem("(nothing yet)", callback=None))

        self.app.menu = [
            self.status_item,
            None,
            self.toggle_item,
            rumps.MenuItem("Copy last transcript", callback=self._copy_last),
            None,
            self.mode_menu,
            self.history_menu,
            None,
            rumps.MenuItem("Edit configuration…", callback=self._edit_config),
            rumps.MenuItem("Reload configuration", callback=self._reload_config),
            rumps.MenuItem("About mumbles", callback=self._about),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _idle_hint(self) -> str:
        verb = "Hold" if self.cfg.activation == "hold" else "Tap"
        return f"{verb} {self.dictation.hotkey_label} to talk"

    def _rebuild_modes(self) -> None:
        rumps = self.rumps
        self.mode_menu.clear()
        for name, mode in sorted(self.cfg.resolved_modes().items()):
            label = f"{'✓ ' if name == self.cfg.active_mode else '   '}{name}"
            self.mode_menu.add(
                rumps.MenuItem(label, callback=self._make_mode_callback(name))
            )

    def _make_mode_callback(self, name: str):
        def callback(_sender):
            self.dictation.set_mode(name)
            self._rebuild_modes()

        return callback

    # --- callbacks from background threads ------------------------------
    def _on_state(self, state: str) -> None:
        self._state = state

    def _on_result(self, text: str, transcript) -> None:
        self._history_dirty = True

    def _on_error(self, exc: Exception) -> None:
        self._notifications.append(str(exc)[:200])

    # --- the main-thread pump -------------------------------------------
    def title_for(self, state: str) -> str:
        """What the bar should read right now. Pure, so it can be tested."""
        if state == RECORDING:
            return f"{GLYPHS[RECORDING]} {self.meter.render()}"
        return GLYPHS.get(state, GLYPHS[IDLE])

    def _tick(self, _timer=None) -> None:
        state = self._state

        if state == RECORDING:
            self.meter.sample()
        elif self.meter.level:
            # Let the bar fall back to rest rather than snapping to empty.
            self.meter.sample()

        title = self.title_for(state)
        if title != self._drawn_title:
            self.app.title = title
            self._drawn_title = title

        toggle = "Stop dictation" if state == RECORDING else "Start dictation"
        if toggle != self._drawn_toggle:
            self.toggle_item.title = toggle
            self._drawn_toggle = toggle

        if self._history_dirty:
            self._history_dirty = False
            self._refresh_history()

        while self._notifications:
            self.rumps.notification(
                "mumbles", "Something went wrong", self._notifications.popleft()
            )

    # --- menu contents ---------------------------------------------------
    def _refresh_history(self) -> None:
        rumps = self.rumps
        self.history_menu.clear()
        entries = self.dictation.history.recent(10)
        if not entries:
            self.history_menu.add(rumps.MenuItem("(nothing yet)", callback=None))
            return
        for entry in entries:
            preview = entry.text.replace("\n", " ")
            if len(preview) > 48:
                preview = preview[:45] + "…"
            self.history_menu.add(
                rumps.MenuItem(preview, callback=self._make_copy_callback(entry.text))
            )

    def _make_copy_callback(self, text: str):
        def callback(_sender):
            inject.set_clipboard(text)

        return callback

    # --- menu actions -----------------------------------------------------
    def _toggle(self, _sender) -> None:
        self.dictation.toggle()

    def _copy_last(self, _sender) -> None:
        if self.dictation.last_text:
            inject.set_clipboard(self.dictation.last_text)
            self.rumps.notification("mumbles", "Copied", self.dictation.last_text[:120])

    def _edit_config(self, _sender) -> None:
        path = paths.config_file()
        self.cfg.save(path)
        subprocess.Popen(["open", "-t", str(path)])

    def _reload_config(self, _sender) -> None:
        self.cfg = config_module.load()
        self.dictation.cfg = self.cfg
        self._rebuild_modes()
        self.status_item.title = self._idle_hint()
        self.rumps.notification("mumbles", "Configuration reloaded", "")

    def _about(self, _sender) -> None:
        from . import __version__

        engine = self.dictation.engine
        self.rumps.alert(
            title=f"mumbles {__version__}",
            message=(
                f"Hotkey: {self.dictation.hotkey_label} ({self.cfg.activation})\n"
                f"Model: {self.cfg.model}\n"
                f"Engine: {engine.name if engine else self.cfg.engine}\n"
                f"Mode: {self.cfg.active_mode}\n\n"
                "Everything runs locally unless a mode calls out to an LLM."
            ),
        )

    def _quit(self, _sender) -> None:
        self.dictation.shutdown()
        self.rumps.quit_application()

    # --- lifecycle --------------------------------------------------------
    def run(self) -> None:
        import threading

        self.dictation.bind_hotkey()

        def warm():
            try:
                self.dictation.warm_up()
            except Exception as exc:
                self._on_error(exc)

        threading.Thread(target=warm, daemon=True).start()

        self.timer = self.rumps.Timer(self._tick, FRAME_INTERVAL)
        self.timer.start()
        self.app.run()


def run(cfg) -> None:
    MenuBarApp(cfg).run()
