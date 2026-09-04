"""Getting text out of mumbles and into whatever app has focus.

The reliable trick on macOS is the same one every dictation tool uses: put
the text on the pasteboard, synthesise Cmd+V, then put the old pasteboard
contents back. Typing character-by-character is the fallback for apps that
block paste.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Optional


class InjectError(RuntimeError):
    pass


def _is_mac() -> bool:
    return sys.platform == "darwin"


# --- clipboard ---------------------------------------------------------


def get_clipboard() -> Optional[str]:
    """Current clipboard text, or None if it holds something else."""
    try:
        if _is_mac():
            proc = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        else:
            proc = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                  capture_output=True, text=True, timeout=5)
        return proc.stdout if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def set_clipboard(text: str) -> None:
    try:
        if _is_mac():
            cmd = ["pbcopy"]
        else:
            cmd = ["xclip", "-selection", "clipboard"]
        proc = subprocess.run(cmd, input=text, text=True, timeout=5)
        if proc.returncode != 0:
            raise InjectError("clipboard write failed")
    except FileNotFoundError as exc:
        raise InjectError(
            "no clipboard tool found (pbcopy on macOS, xclip on Linux)"
        ) from exc
    except subprocess.SubprocessError as exc:
        raise InjectError(f"clipboard write failed: {exc}") from exc


# --- keystrokes --------------------------------------------------------


def _paste_pynput() -> bool:
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return False
    try:
        keyboard = Controller()
        modifier = Key.cmd if _is_mac() else Key.ctrl
        with keyboard.pressed(modifier):
            keyboard.press("v")
            keyboard.release("v")
        return True
    except Exception:
        return False


def _paste_osascript() -> bool:
    if not _is_mac():
        return False
    script = 'tell application "System Events" to keystroke "v" using command down'
    try:
        proc = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=10)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def send_paste() -> None:
    """Synthesise the paste shortcut for the frontmost app."""
    if _paste_pynput() or _paste_osascript():
        return
    raise InjectError(
        "could not send Cmd+V. Grant Accessibility permission to your terminal "
        "(or to mumbles) in System Settings > Privacy & Security > Accessibility."
    )


def type_text(text: str, delay: float = 0.0) -> None:
    """Fallback: type the text directly. Slower, but survives paste-blockers."""
    try:
        from pynput.keyboard import Controller
    except ImportError as exc:
        raise InjectError("pynput is required to type text") from exc
    keyboard = Controller()
    for char in text:
        keyboard.type(char)
        if delay:
            time.sleep(delay)


# --- the thing you actually call ---------------------------------------


def deliver(
    text: str,
    auto_paste: bool = True,
    restore_clipboard: bool = True,
    restore_delay: float = 0.35,
) -> str:
    """Put `text` where the user wants it. Returns what actually happened.

    Result is one of "pasted", "typed" or "clipboard".
    """
    if not text:
        return "clipboard"

    previous = get_clipboard() if (auto_paste and restore_clipboard) else None
    set_clipboard(text)

    if not auto_paste:
        return "clipboard"

    outcome = "pasted"
    try:
        # The frontmost app needs a beat to notice the new pasteboard contents.
        time.sleep(0.05)
        send_paste()
    except InjectError:
        try:
            type_text(text)
            outcome = "typed"
        except InjectError:
            return "clipboard"

    if previous is not None:
        # Restoring immediately would race the paste we just triggered.
        time.sleep(restore_delay)
        try:
            set_clipboard(previous)
        except InjectError:
            pass
    return outcome
