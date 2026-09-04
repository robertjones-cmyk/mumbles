"""Start mumbles at login via a LaunchAgent."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LABEL = "com.mumbles.dictation"

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{arguments}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{path}</string>
  </dict>
</dict>
</plist>
"""


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _executable() -> list:
    """How to relaunch mumbles: the installed script if there is one."""
    from shutil import which

    script = which("mumbles")
    if script:
        return [script, "run"]
    return [sys.executable, "-m", "mumbles", "run"]


def install(log_path: Path) -> Path:
    if sys.platform != "darwin":
        raise SystemExit("autostart is macOS-only")
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    arguments = "\n".join(f"    <string>{arg}</string>" for arg in _executable())
    target.write_text(
        PLIST.format(
            label=LABEL,
            arguments=arguments,
            log=log_path,
            path=os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        )
    )
    subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(target)], capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise SystemExit(f"launchctl load failed: {result.stderr.strip()}")
    return target


def uninstall() -> bool:
    target = plist_path()
    if not target.exists():
        return False
    subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
    target.unlink()
    return True


def installed() -> bool:
    return plist_path().exists()
