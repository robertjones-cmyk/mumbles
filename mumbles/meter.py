"""A peak-decay level meter for the menu bar.

The audio callback pushes raw RMS values in from PortAudio's thread; the UI
samples them from the main thread. Keeping the two apart matters: AppKit is
not safe to touch from the audio thread, and the audio thread must never
block on a redraw.
"""

from __future__ import annotations

import math
import threading

# Speech sits far below full scale. Mapping 0 dBFS to a full bar would leave
# the meter looking dead during normal talking, so the window is tightened
# to the range a voice actually occupies.
FLOOR_DB = -55.0
CEILING_DB = -10.0

# Eight bar heights, all one cell wide, so the rendered meter never changes
# width and neighbouring menu bar icons stay put.
LEVELS = "▁▂▃▄▅▆▇█"

DEFAULT_WIDTH = 6
DEFAULT_DECAY = 0.72


def rms_to_unit(rms: float, floor_db: float = FLOOR_DB,
                ceiling_db: float = CEILING_DB) -> float:
    """Map an RMS amplitude to 0.0-1.0 on a decibel scale."""
    if rms <= 0.0 or not math.isfinite(rms):
        return 0.0
    db = 20.0 * math.log10(rms)
    if db <= floor_db:
        return 0.0
    if db >= ceiling_db:
        return 1.0
    return (db - floor_db) / (ceiling_db - floor_db)


def render_bar(level: float, width: int = DEFAULT_WIDTH) -> str:
    """Draw `level` (0.0-1.0) as a fixed-width row of block characters."""
    level = min(max(level, 0.0), 1.0)
    cells = []
    for index in range(width):
        # How much of this cell the level covers, as 0.0-1.0.
        fill = min(max((level - index / width) * width, 0.0), 1.0)
        cells.append(LEVELS[round(fill * (len(LEVELS) - 1))])
    return "".join(cells)


class LevelMeter:
    """Collects peaks between UI frames and decays them smoothly."""

    def __init__(self, width: int = DEFAULT_WIDTH,
                 decay: float = DEFAULT_DECAY) -> None:
        self.width = width
        self.decay = decay
        self._pending_peak = 0.0
        self._level = 0.0
        self._lock = threading.Lock()

    @property
    def level(self) -> float:
        return self._level

    def push(self, rms: float) -> None:
        """Called from the audio thread, many times per UI frame."""
        with self._lock:
            if rms > self._pending_peak:
                self._pending_peak = rms

    def sample(self) -> float:
        """Called from the UI thread once per frame. Advances the meter.

        Takes the loudest value seen since the last call so short peaks are
        never missed, then decays toward silence when the room goes quiet.
        """
        with self._lock:
            peak, self._pending_peak = self._pending_peak, 0.0
        self._level = max(rms_to_unit(peak), self._level * self.decay)
        if self._level < 0.01:
            self._level = 0.0
        return self._level

    def render(self) -> str:
        return render_bar(self._level, self.width)

    def reset(self) -> None:
        with self._lock:
            self._pending_peak = 0.0
        self._level = 0.0
