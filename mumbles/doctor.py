"""`mumbles doctor` - check that every moving part is actually in place."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List

from . import paths


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


def _check_platform() -> Check:
    if sys.platform == "darwin":
        return Check("platform", True, "macOS")
    return Check(
        "platform", False, sys.platform,
        "mumbles targets macOS; paste and sounds will not work here.",
    )


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 9)
    return Check("python", ok, version, "Python 3.9 or newer is required.")


def _check_import(module: str, name: str, fix: str) -> Check:
    try:
        __import__(module)
        return Check(name, True, "installed")
    except ImportError as exc:
        return Check(name, False, str(exc)[:120], fix)
    except Exception as exc:
        # Installed, but it cannot initialise here - a missing system library
        # or a permission the OS has not granted yet. `fix` would mislead.
        return Check(name, False, f"installed but not usable: {str(exc)[:100]}")


def _check_microphone() -> Check:
    try:
        from .audio import list_devices

        devices = list_devices()
    except Exception as exc:
        return Check("microphone", False, str(exc)[:160],
                     "brew install portaudio && pip install sounddevice")
    if not devices:
        return Check("microphone", False, "no input devices",
                     "Check System Settings > Privacy & Security > Microphone.")
    return Check("microphone", True, f"{len(devices)} input device(s): "
                 + ", ".join(d["name"] for d in devices[:3]))


def _check_engines() -> Check:
    from .transcribe import available_engines, is_apple_silicon

    engines = available_engines()
    if not engines:
        return Check(
            "speech engine", False, "none installed",
            "pip install mlx-whisper" if is_apple_silicon()
            else "pip install faster-whisper",
        )
    return Check("speech engine", True, ", ".join(engines))


def _check_accessibility() -> Check:
    """Can we synthesise keystrokes? The paste step depends on it."""
    if sys.platform != "darwin":
        return Check("accessibility", True, "not applicable")
    script = 'tell application "System Events" to get name of first process'
    try:
        proc = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("accessibility", False, str(exc)[:120], "")
    if proc.returncode == 0:
        return Check("accessibility", True, "keystroke synthesis permitted")
    return Check(
        "accessibility", False, proc.stderr.strip()[:160],
        "System Settings > Privacy & Security > Accessibility: add your "
        "terminal (or mumbles) and switch it on.",
    )


def _check_clipboard() -> Check:
    tool = "pbcopy" if sys.platform == "darwin" else "xclip"
    if shutil.which(tool):
        return Check("clipboard", True, tool)
    return Check("clipboard", False, f"{tool} not found",
                 "" if sys.platform == "darwin" else "sudo apt install xclip")


def _check_config() -> Check:
    from . import config as config_module

    try:
        cfg = config_module.load()
    except SystemExit as exc:
        return Check("config", False, str(exc), "Fix or delete the config file.")
    from .hotkey import HotkeyError, parse_combo

    try:
        parse_combo(cfg.hotkey)
    except HotkeyError as exc:
        return Check("config", False, str(exc), "Set a valid `hotkey`.")
    if cfg.active_mode not in cfg.resolved_modes():
        return Check("config", False, f"unknown mode {cfg.active_mode!r}",
                     "Run: mumbles mode clean")
    return Check("config", True, str(paths.config_file()))


def run_checks() -> List[Check]:
    return [
        _check_platform(),
        _check_python(),
        _check_config(),
        _check_import("numpy", "numpy", "pip install numpy"),
        _check_import("sounddevice", "sounddevice", "pip install sounddevice"),
        _check_import("pynput", "pynput", "pip install pynput"),
        _check_import("rumps", "rumps (menu bar)", "pip install rumps"),
        _check_microphone(),
        _check_engines(),
        _check_clipboard(),
        _check_accessibility(),
    ]
