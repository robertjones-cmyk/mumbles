"""Short audio cues so you know the mic is live without looking."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SYSTEM_SOUNDS = Path("/System/Library/Sounds")

CUES = {
    "start": "Tink.aiff",
    "stop": "Pop.aiff",
    "done": "Glass.aiff",
    "error": "Basso.aiff",
    "cancel": "Funk.aiff",
}


def play(cue: str, enabled: bool = True) -> None:
    """Fire-and-forget. Never blocks and never raises."""
    if not enabled or sys.platform != "darwin":
        return
    sound = _SYSTEM_SOUNDS / CUES.get(cue, "Tink.aiff")
    if not sound.exists():
        return
    try:
        subprocess.Popen(
            ["afplay", str(sound)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        pass
