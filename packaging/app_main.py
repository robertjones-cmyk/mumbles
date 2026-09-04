"""Entry point for the bundled macOS app.

Double-clicking mumbles.app starts the menu bar UI directly, with no
arguments and no terminal. Anything that goes wrong before the UI exists has
nowhere to print, so it is written to the log and shown as an alert.
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
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
