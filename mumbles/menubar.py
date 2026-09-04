"""macOS menu bar UI (requires `rumps`).

The bar item is the whole interface: a glyph shows state at a glance, and
the menu holds mode switching, recent transcripts and preferences.
"""

from __future__ import annotations

import subprocess
import threading
from . import config as config_module
from . import inject, paths
from .app import IDLE, RECORDING, TRANSCRIBING, DictationApp

GLYPHS = {IDLE: "🎙", RECORDING: "🔴", TRANSCRIBING: "✍️"}


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
        self.dictation = DictationApp(
            cfg,
            on_state=self._on_state,
            on_result=self._on_result,
            on_error=self._on_error,
        )
        self._build_menu()

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        rumps = self.rumps
        self.toggle_item = rumps.MenuItem("Start dictation", callback=self._toggle)
        self.status_item = rumps.MenuItem(
            f"Hold {self.dictation.hotkey_label} to talk", callback=None
        )

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

    def _rebuild_modes(self) -> None:
        rumps = self.rumps
        self.mode_menu.clear()
        for name, mode in sorted(self.cfg.resolved_modes().items()):
            label = f"{'✓ ' if name == self.cfg.active_mode else '   '}{name}"
            item = rumps.MenuItem(label, callback=self._make_mode_callback(name))
            self.mode_menu.add(item)

    def _make_mode_callback(self, name: str):
        def callback(_sender):
            self.dictation.set_mode(name)
            self._rebuild_modes()
            self.rumps.notification("mumbles", "Mode changed", name)

        return callback

    # ------------------------------------------------------------------
    def _on_state(self, state: str) -> None:
        self.app.title = GLYPHS.get(state, GLYPHS[IDLE])
        self.toggle_item.title = (
            "Stop dictation" if state == RECORDING else "Start dictation"
        )

    def _on_result(self, text: str, transcript) -> None:
        self._refresh_history()

    def _on_error(self, exc: Exception) -> None:
        self.rumps.notification("mumbles", "Something went wrong", str(exc)[:200])

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

    # ------------------------------------------------------------------
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
        self.status_item.title = f"Hold {self.dictation.hotkey_label} to talk"
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

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.dictation.bind_hotkey()
        self._refresh_history()

        def warm():
            try:
                self.dictation.warm_up()
            except Exception as exc:
                self._on_error(exc)

        threading.Thread(target=warm, daemon=True).start()
        self.app.run()


def run(cfg) -> None:
    MenuBarApp(cfg).run()
