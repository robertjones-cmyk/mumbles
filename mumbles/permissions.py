"""macOS permission and translocation checks.

The hotkey needs Accessibility. Without it pynput prints a warning to a
stderr nobody sees and then silently never fires, which looks exactly like a
broken app. These checks let the UI say what is actually wrong.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

_AX_FRAMEWORK = ("/System/Library/Frameworks/ApplicationServices.framework"
                 "/ApplicationServices")

# Deep links into the relevant System Settings panes.
ACCESSIBILITY_PANE = ("x-apple.systempreferences:com.apple.preference.security"
                      "?Privacy_Accessibility")
INPUT_MONITORING_PANE = ("x-apple.systempreferences:com.apple.preference.security"
                         "?Privacy_ListenEvent")
MICROPHONE_PANE = ("x-apple.systempreferences:com.apple.preference.security"
                   "?Privacy_Microphone")


def is_mac() -> bool:
    return sys.platform == "darwin"


def accessibility_trusted() -> bool:
    """True when this process may synthesise and observe keystrokes.

    Calls AXIsProcessTrusted through ctypes rather than pyobjc, so it adds no
    dependency and cannot be the thing that breaks an app bundle.
    """
    if not is_mac():
        return True
    try:
        lib = ctypes.cdll.LoadLibrary(_AX_FRAMEWORK)
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except (OSError, AttributeError):
        return True  # cannot tell; do not cry wolf


def translocated_path() -> str:
    """The randomised read-only path macOS is running us from, if any.

    Gatekeeper translocates a quarantined app on every launch. The path
    changes each time, so any permission the user grants is attached to a
    copy that will not exist next time - the app looks permanently unable to
    remember its permissions.
    """
    executable = os.path.abspath(sys.executable)
    return executable if "/AppTranslocation/" in executable else ""


def is_translocated() -> bool:
    return bool(translocated_path())


def bundle_path() -> str:
    """The .app this process lives in, or "" when running from source."""
    path = os.path.abspath(sys.executable)
    marker = ".app/Contents/"
    index = path.find(marker)
    return path[: index + 4] if index != -1 else ""


def open_settings(pane: str) -> bool:
    if not is_mac():
        return False
    try:
        return subprocess.run(["open", pane], capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def quarantine_fix_command() -> str:
    """The command that stops macOS translocating this app."""
    app = bundle_path() or "/Applications/mumbles.app"
    if is_translocated():
        # The translocated copy is a throwaway; the real one is in Applications.
        app = "/Applications/mumbles.app"
    return f"xattr -dr com.apple.quarantine {app}"


def problems() -> list:
    """Everything standing between the user and a working hotkey.

    Each entry is (short_label, explanation, remedy_pane_or_empty).
    """
    found = []
    if is_translocated():
        found.append((
            "macOS is running a quarantined copy",
            "Gatekeeper relaunches this app from a new random location every "
            "time, so any permission you grant is forgotten immediately. Run "
            "this in Terminal, then reopen the app:\n\n"
            f"    {quarantine_fix_command()}",
            "",
        ))
    if not accessibility_trusted():
        found.append((
            "Accessibility permission is missing",
            "Without it the global hotkey never fires and nothing can be "
            "pasted. Add mumbles under Privacy & Security > Accessibility, "
            "and under Input Monitoring.",
            ACCESSIBILITY_PANE,
        ))
    return found
