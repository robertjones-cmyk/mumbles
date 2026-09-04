"""Global hotkey handling.

Two activation styles:

  hold    - push-to-talk. Recording lives exactly as long as the keys are down.
  toggle  - tap once to start, tap again to stop.

Combos use pynput's notation: modifiers in angle brackets, joined by "+".
Examples: "<cmd>+<shift>+space", "<ctrl>+<alt>+d", "<f5>".
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional, Set

# Friendly aliases so a config file can say "cmd" or "option" and still work.
_ALIASES = {
    "command": "cmd",
    "super": "cmd",
    "win": "cmd",
    "meta": "cmd",
    "option": "alt",
    "opt": "alt",
    "control": "ctrl",
    "return": "enter",
    "escape": "esc",
    "spacebar": "space",
}

MODIFIERS = {"cmd", "ctrl", "alt", "shift", "cmd_r", "ctrl_r", "alt_r", "shift_r"}


class HotkeyError(RuntimeError):
    pass


def parse_combo(combo: str) -> List[str]:
    """Normalise a combo string into a list of lowercase key tokens.

    Modifier brackets are stripped; the result is comparison-ready and needs
    no pynput import, which keeps it testable anywhere.
    """
    if not combo or not combo.strip():
        raise HotkeyError("hotkey is empty")
    tokens: List[str] = []
    for part in combo.split("+"):
        token = part.strip().lower()
        if not token:
            raise HotkeyError(f"malformed hotkey {combo!r}")
        if token.startswith("<") and token.endswith(">"):
            token = token[1:-1]
        token = _ALIASES.get(token, token)
        if not token:
            raise HotkeyError(f"malformed hotkey {combo!r}")
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        raise HotkeyError(f"malformed hotkey {combo!r}")
    return tokens


def format_combo(tokens: List[str]) -> str:
    """Render tokens back to pynput notation, for display and round-tripping."""
    return "+".join(f"<{t}>" if t in MODIFIERS or len(t) > 1 else t for t in tokens)


def pretty_combo(tokens: List[str]) -> str:
    """Mac-style glyphs for the menu bar: ⌘⇧Space."""
    glyphs = {"cmd": "⌘", "shift": "⇧", "alt": "⌥", "ctrl": "⌃",
              "cmd_r": "⌘", "shift_r": "⇧", "alt_r": "⌥", "ctrl_r": "⌃"}
    out = ""
    for token in tokens:
        out += glyphs.get(token, token.capitalize() if len(token) > 1 else token.upper())
    return out


def _canonical_token(key, listener) -> Optional[str]:
    """Map a pynput key event to one of our normalised tokens."""
    from pynput import keyboard

    try:
        key = listener.canonical(key)
    except Exception:
        pass
    if isinstance(key, keyboard.Key):
        name = key.name.lower()
        # Treat left/right modifiers as the same key for matching purposes.
        if name.endswith("_l") or name.endswith("_r"):
            name = name[:-2]
        return _ALIASES.get(name, name)
    char = getattr(key, "char", None)
    if char:
        return char.lower()
    vk = getattr(key, "vk", None)
    return f"vk{vk}" if vk is not None else None


class HotkeyListener:
    """Watches the keyboard globally and drives start/stop callbacks."""

    def __init__(
        self,
        combo: str,
        activation: str = "hold",
        on_activate: Optional[Callable[[], None]] = None,
        on_deactivate: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        cancel_key: str = "esc",
    ) -> None:
        self.tokens = parse_combo(combo)
        self.combo = combo
        self.activation = activation if activation in ("hold", "toggle") else "hold"
        self.on_activate = on_activate or (lambda: None)
        self.on_deactivate = on_deactivate or (lambda: None)
        self.on_cancel = on_cancel
        self.cancel_key = _ALIASES.get(cancel_key.lower(), cancel_key.lower())
        self._pressed: Set[str] = set()
        self._engaged = False
        self._toggled_on = False
        self._listener = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self._toggled_on if self.activation == "toggle" else self._engaged

    def _all_down(self) -> bool:
        return all(token in self._pressed for token in self.tokens)

    def _handle_press(self, token: Optional[str]) -> None:
        if token is None:
            return
        if (self.on_cancel is not None and token == self.cancel_key
                and token not in self.tokens and self.active):
            self._toggled_on = False
            self._engaged = False
            self.on_cancel()
            return
        with self._lock:
            if token in self._pressed:
                return  # key repeat
            self._pressed.add(token)
            fires = self._all_down() and not self._engaged
            if fires:
                self._engaged = True
        if not fires:
            return
        if self.activation == "toggle":
            self._toggled_on = not self._toggled_on
            (self.on_activate if self._toggled_on else self.on_deactivate)()
        else:
            self.on_activate()

    def _handle_release(self, token: Optional[str]) -> None:
        if token is None:
            return
        with self._lock:
            self._pressed.discard(token)
            was_engaged = self._engaged
            still_down = self._all_down()
            if was_engaged and not still_down:
                self._engaged = False
        if was_engaged and not still_down and self.activation == "hold":
            self.on_deactivate()

    # ------------------------------------------------------------------
    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise HotkeyError("pynput is not installed. Run: pip install pynput") from exc

        listener_ref = {}

        def on_press(key):
            self._handle_press(_canonical_token(key, listener_ref["listener"]))

        def on_release(key):
            self._handle_release(_canonical_token(key, listener_ref["listener"]))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener_ref["listener"] = self._listener
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def join(self) -> None:
        if self._listener is not None:
            self._listener.join()
