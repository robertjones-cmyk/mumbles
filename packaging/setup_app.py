"""py2app build configuration.

Produces `dist/mumbles.app`: a menu bar agent with no Dock icon, carrying its
own Python and every dependency, so a user only has to drag it to
Applications.

Build it with:  python packaging/setup_app.py py2app
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

from setuptools import setup

# py2app refuses to run against a Distribution carrying install_requires, and
# setuptools fills that in from any pyproject.toml in the working directory.
# make_dmg.sh therefore copies this file to a staging directory with no
# pyproject.toml in it and points us back at the real tree from here.
ROOT = Path(os.environ.get("MUMBLES_SOURCE_ROOT")
            or Path(__file__).resolve().parent.parent).resolve()
sys.path.insert(0, str(ROOT))

from mumbles import __version__  # noqa: E402

ICON = ROOT / "packaging" / "mumbles.icns"

# Packages py2app cannot discover by following imports, either because we
# import them lazily on purpose or because they load things at runtime.
INCLUDES = [
    # sounddevice is a single module, not a package, so it belongs here.
    "sounddevice",
    "_sounddevice",
    "sqlite3",
    "urllib.request",
]

# py2app resolves `packages` names with the deprecated imp module, and
# imp.find_module cannot resolve mlx: it ships as a namespace-style package
# split across the mlx and mlx-metal distributions. Listing it here aborts the
# build outright, so it goes in `includes` instead, where py2app resolves
# through modulegraph rather than imp.
OPTIONAL_BACKENDS = ["mlx_whisper", "faster_whisper", "ctranslate2"]
OPTIONAL_INCLUDES = ["mlx", "mlx.core", "mlx.nn"]


def _installed(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# Real packages only: py2app resolves these with imp.find_module, and being
# listed here also means py2app copies them as directories instead of zipping
# them - which is what lets a bundled .dylib be dlopen'd at all.
#
# _sounddevice_data carries libportaudio.dylib. sounddevice tries the system
# library first and falls back to this package's __path__, and on a clean Mac
# with no Homebrew portaudio the fallback is the only path that works. Zipped,
# the dylib cannot be loaded and audio capture dies at import.
_REQUIRED_PACKAGES = ("mumbles", "rumps", "pynput", "numpy", "_sounddevice_data")

PACKAGES = [name for name in _REQUIRED_PACKAGES if _installed(name)]
PACKAGES += [name for name in OPTIONAL_BACKENDS if _installed(name)]
INCLUDES += [name for name in OPTIONAL_INCLUDES if _installed(name)]

PLIST = {
    "CFBundleName": "mumbles",
    "CFBundleDisplayName": "mumbles",
    "CFBundleIdentifier": "com.mumbles.app",
    "CFBundleVersion": __version__,
    "CFBundleShortVersionString": __version__,
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

def _build() -> None:
    setup(
        name="mumbles",
        version=__version__,
        app=[str(ROOT / "packaging" / "app_main.py")],
        options=OPTIONS,
    )


def main() -> int:
    """Run py2app with room to recurse.

    py2app walks every dependency's AST to build its module graph, and the
    scientific stack is deep enough to exhaust the default 1000-frame limit.
    Raising the limit alone just trades a RecursionError for a segfault when
    the C stack runs out, so the build also gets a thread with a large stack
    to run on.
    """
    sys.setrecursionlimit(15000)
    threading.stack_size(64 * 1024 * 1024)

    failure: list = []

    def target() -> None:
        try:
            _build()
        except SystemExit as exc:               # distutils signals errors this way
            if exc.code not in (0, None):
                # The message is carried as the exit code; print it or the
                # build fails with no explanation at all.
                print(f"py2app failed: {exc.code}", file=sys.stderr)
                failure.append(exc)
        except BaseException as exc:
            traceback.print_exc()
            failure.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
