"""Microphone capture.

A recorder streams mono float32 at the model's native 16 kHz, buffers the
frames in memory, and hands back one numpy array when you stop. Nothing is
written to disk unless `keep_recordings` is on.
"""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from typing import Callable, List, Optional


class AudioError(RuntimeError):
    pass


def _import_sounddevice():
    try:
        import sounddevice as sd  # noqa: WPS433 (deliberately lazy)
    except OSError as exc:  # PortAudio missing at the OS level
        raise AudioError(
            "PortAudio is not available. On macOS: brew install portaudio"
        ) from exc
    except ImportError as exc:
        raise AudioError(
            "sounddevice is not installed. Run: pip install sounddevice"
        ) from exc
    return sd


def _import_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise AudioError("numpy is not installed. Run: pip install numpy") from exc
    return np


def list_devices() -> List[dict]:
    """Input devices, as dicts with index/name/channels/default_samplerate."""
    sd = _import_sounddevice()
    devices = []
    for index, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "index": index,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "default_samplerate": dev.get("default_samplerate"),
                }
            )
    return devices


def resolve_device(name: Optional[str]):
    """Match a configured device by index, exact name, or substring."""
    if name in (None, "", "default"):
        return None
    if isinstance(name, int) or (isinstance(name, str) and name.isdigit()):
        return int(name)
    lowered = str(name).lower()
    for dev in list_devices():
        if dev["name"].lower() == lowered:
            return dev["index"]
    for dev in list_devices():
        if lowered in dev["name"].lower():
            return dev["index"]
    raise AudioError(f"no input device matching {name!r}")


class Recorder:
    """Start/stop microphone capture. One recorder, reused for every take."""

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[str] = None,
        max_seconds: int = 300,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.device = device
        self.max_seconds = max_seconds
        self.on_level = on_level
        self._frames: List["object"] = []
        self._stream = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._truncated = False

    # ------------------------------------------------------------------
    @property
    def recording(self) -> bool:
        return self._stream is not None

    @property
    def elapsed(self) -> float:
        return 0.0 if self._started_at is None else time.monotonic() - self._started_at

    @property
    def truncated(self) -> bool:
        """True when the take hit `max_seconds` and was cut short."""
        return self._truncated

    # ------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        np = _import_numpy()
        with self._lock:
            if self._stream is None:
                return
            self._frames.append(indata.copy())
            total = sum(len(f) for f in self._frames)
        if self.on_level is not None:
            try:
                self.on_level(float(np.sqrt(np.mean(np.square(indata)))))
            except Exception:  # a UI meter must never kill the stream
                pass
        if total >= self.max_seconds * self.sample_rate:
            self._truncated = True
            threading.Thread(target=self._abort_stream, daemon=True).start()

    def _abort_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.recording:
            return
        sd = _import_sounddevice()
        with self._lock:
            self._frames = []
        self._truncated = False
        self._started_at = time.monotonic()
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=resolve_device(self.device),
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise AudioError(
                f"could not open the microphone: {exc}. On macOS, grant "
                "Microphone access in System Settings > Privacy & Security."
            ) from exc

    def stop(self):
        """Stop capture and return the recorded mono float32 samples."""
        np = _import_numpy()
        self._abort_stream()
        with self._lock:
            frames, self._frames = self._frames, []
        if not frames:
            return np.zeros(0, dtype="float32")
        return np.concatenate(frames, axis=0).reshape(-1).astype("float32")

    def cancel(self) -> None:
        """Throw the take away without transcribing it."""
        self._abort_stream()
        with self._lock:
            self._frames = []


def duration_seconds(samples, sample_rate: int) -> float:
    return len(samples) / float(sample_rate) if sample_rate else 0.0


def peak_level(samples) -> float:
    np = _import_numpy()
    return float(np.max(np.abs(samples))) if len(samples) else 0.0


def write_wav(samples, sample_rate: int, path: Path) -> Path:
    """16-bit PCM WAV. Used for whisper.cpp and for `keep_recordings`."""
    np = _import_numpy()
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path):
    """Read a WAV into mono float32, resampling naively if needed."""
    np = _import_numpy()
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        raise AudioError(f"{path}: only 16-bit WAV files are supported")
    data = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def resample(samples, source_rate: int, target_rate: int):
    """Linear resample. Good enough for speech fed to Whisper."""
    np = _import_numpy()
    if source_rate == target_rate or len(samples) == 0:
        return samples
    count = int(round(len(samples) * target_rate / float(source_rate)))
    source_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    target_x = np.linspace(0.0, 1.0, num=count, endpoint=False)
    return np.interp(target_x, source_x, samples).astype("float32")
