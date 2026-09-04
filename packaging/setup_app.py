"""py2app build configuration.

Produces `dist/mumbles.app`: a menu bar agent with no Dock icon, carrying its
own Python and every dependency, so a user only has to drag it to
Applications.

Build it with:  python packaging/setup_app.py py2app
"""

from __future__ import annotations

import sys
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mumbles import __version__  # noqa: E402

ICON = ROOT / "packaging" / "mumbles.icns"

# Packages py2app cannot discover by following imports, either because we
# import them lazily on purpose or because they load things at runtime.
INCLUDES = [
    "mumbles",
    "rumps",
    "pynput",
    "sounddevice",
    "numpy",
    "sqlite3",
    "urllib.request",
]

OPTIONAL_BACKENDS = ["mlx_whisper", "mlx", "faster_whisper", "ctranslate2"]


def _installed(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


PACKAGES = [name for name in ("rumps", "pynput", "sounddevice", "numpy")
            if _installed(name)]
PACKAGES += [name for name in OPTIONAL_BACKENDS if _installed(name)]

PLIST = {
    "CFBundleName": "mumbles",
    "CFBundleDisplayName": "mumbles",
    "CFBundleIdentifier": "com.mumbles.app",
    "CFBundleVersion": __version__,
    "CFBundleShortVersionString": __version__,
    "CFBundleExecutable": "mumbles",
    "LSMinimumSystemVersion": "12.0",
    "NSHighResolutionCapable": True,
    # A menu bar agent: no Dock icon, no app switcher entry.
    "LSUIElement": True,
    # macOS refuses microphone access outright without this string, and the
    # app is terminated the moment it opens an input stream.
    "NSMicrophoneUsageDescription":
        "mumbles transcribes your speech on this Mac so you can dictate into "
        "any app.",
    "NSAppleEventsUsageDescription":
        "mumbles sends a paste keystroke so your dictation lands in the app "
        "you are using.",
}

OPTIONS = {
    "py2app": {
        "argv_emulation": False,   # breaks global hotkey handling
        "packages": PACKAGES,
        "includes": INCLUDES,
        "plist": PLIST,
        "iconfile": str(ICON) if ICON.exists() else None,
        "excludes": ["tkinter", "PyQt5", "PySide2", "matplotlib", "pytest"],
        "optimize": 1,
    }
}

if OPTIONS["py2app"]["iconfile"] is None:
    del OPTIONS["py2app"]["iconfile"]

setup(
    name="mumbles",
    version=__version__,
    app=[str(ROOT / "packaging" / "app_main.py")],
    options=OPTIONS,
    setup_requires=["py2app"],
)
