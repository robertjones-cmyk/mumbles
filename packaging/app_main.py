"""Entry point for the bundled macOS app.

Double-clicking mumbles.app starts the menu bar UI directly, with no
arguments and no terminal. Anything that goes wrong before the UI exists has
nowhere to print, so it is written to the log and shown as an alert.
"""

from __future__ import annotations

import os
import sys
import traceback


def selftest() -> int:
    """Import everything the app needs and report, without starting the UI.

    A py2app bundle can build cleanly and still be missing a package that was
    only ever imported lazily. Running this inside the bundle is what proves
    the interpreter it shipped with can actually reach them.
    """
    import importlib
    import platform

    required = ["mumbles", "mumbles.menubar", "mumbles.meter", "mumbles.app",
                "mumbles.audio", "mumbles.transcribe", "mumbles.cli",
                "rumps", "pynput", "sounddevice", "numpy", "sqlite3"]
    missing = []
    for name in required:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append(f"{name}: {exc}")

    from mumbles.transcribe import available_engines

    engines = available_engines()
    print(f"python      {platform.python_version()} ({platform.machine()})")
    print(f"engines     {', '.join(engines) or 'NONE'}")
    for name in required:
        print(f"  {'FAIL' if any(m.startswith(name + ':') for m in missing) else 'ok'}"
              f"  {name}")
    for failure in missing:
        print(f"MISSING {failure}", file=sys.stderr)
    if not engines:
        print("MISSING no speech backend in the bundle", file=sys.stderr)
    return 1 if (missing or not engines) else 0


def main() -> int:
    # Set by CI, and useful for debugging an install: prove the bundle is
    # complete without needing a screen, a microphone or a click.
    if os.environ.get("MUMBLES_SELFTEST"):
        return selftest()

    from mumbles import config as config_module
    from mumbles import paths

    paths.ensure_dirs()
    cfg = config_module.load()

    from mumbles import menubar

    menubar.run(cfg)
    return 0


def _report(message: str) -> None:
    from mumbles import paths

    try:
        paths.ensure_dirs()
        with paths.log_file().open("a") as handle:
            handle.write(message + "\n")
    except Exception:
        pass
    try:
        import subprocess

        subprocess.run([
            "osascript", "-e",
            'display alert "mumbles could not start" message '
            f'{message.splitlines()[-1][:300]!r}',
        ], capture_output=True)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        _report(traceback.format_exc())
        sys.exit(1)
