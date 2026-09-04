"""Render the app icon as a 1024x1024 PNG, using only the standard library.

Shapes are signed distance fields so edges can be antialiased analytically -
no image library, no checked-in binary, and the icon is reproducible.
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

SIZE = 1024

# Indigo to violet, top-left to bottom-right.
TOP = (99, 91, 255)
BOTTOM = (168, 85, 247)


def _rounded_box(px: float, py: float, half_w: float, half_h: float,
                 radius: float) -> float:
    """Signed distance to a rounded rectangle centred on the origin."""
    dx = abs(px) - half_w + radius
    dy = abs(py) - half_h + radius
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    return outside + min(max(dx, dy), 0.0) - radius


def _ring_segment(px: float, py: float, radius: float, thickness: float) -> float:
    """Lower half of an annulus: the microphone's cradle."""
    distance = abs(math.hypot(px, py) - radius) - thickness / 2.0
    if py < 0:
        # Square off the ends rather than letting the ring close.
        distance = max(distance, -py)
    return distance


def _coverage(distance: float, softness: float = 1.2) -> float:
    """Antialias: 1 inside the shape, 0 outside, a smooth ramp at the edge."""
    return min(max(0.5 - distance / softness, 0.0), 1.0)


def _blend(base, layer, alpha):
    return tuple(round(b + (l - b) * alpha) for b, l in zip(base, layer))


def render(size: int = SIZE) -> bytes:
    scale = size / 1024.0
    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter byte: none
        for x in range(size):
            # Centre-relative coordinates in a 1024-space.
            px = (x + 0.5) / scale - 512.0
            py = (y + 0.5) / scale - 512.0

            background = _coverage(_rounded_box(px, py, 460, 460, 232))
            if background <= 0.0:
                row.extend((0, 0, 0, 0))
                continue

            mix = ((x / size) + (y / size)) / 2.0
            colour = tuple(round(t + (b - t) * mix) for t, b in zip(TOP, BOTTOM))

            # The group is nudged up so it reads as optically centred.
            capsule = _coverage(_rounded_box(px, py + 175, 96, 190, 96))
            cradle = _coverage(_ring_segment(px, py + 115, 232, 46))
            stem = _coverage(_rounded_box(px, py - 275, 22, 78, 22))
            base = _coverage(_rounded_box(px, py - 345, 118, 24, 24))

            white = max(capsule, cradle, stem, base)
            if white > 0.0:
                colour = _blend(colour, (255, 255, 255), white)

            alpha = round(255 * background)
            row.extend((colour[0], colour[1], colour[2], alpha))
        rows.append(bytes(row))
    return b"".join(rows)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def write_png(path: Path, size: int = SIZE) -> Path:
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    body = zlib.compress(render(size), 9)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", body)
        + _chunk(b"IEND", b"")
    )
    return path


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "packaging/mumbles.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"wrote {write_png(target)}")
