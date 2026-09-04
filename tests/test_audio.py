"""WAV and resampling tests. Skipped where numpy is unavailable."""

import math

import pytest

np = pytest.importorskip("numpy")

from mumbles import audio  # noqa: E402


def _tone(seconds=0.5, rate=16000, freq=440.0):
    t = np.arange(int(seconds * rate)) / float(rate)
    return (0.5 * np.sin(2 * math.pi * freq * t)).astype("float32")


def test_wav_round_trip_preserves_the_signal(tmp_path):
    original = _tone()
    path = audio.write_wav(original, 16000, tmp_path / "tone.wav")
    assert path.exists()

    restored, rate = audio.read_wav(path)
    assert rate == 16000
    assert len(restored) == len(original)
    # 16-bit quantisation is the only loss.
    assert float(np.max(np.abs(restored - original))) < 1e-3


def test_stereo_is_mixed_down_to_mono(tmp_path):
    left, right = _tone(freq=440.0), _tone(freq=880.0)
    interleaved = np.empty(len(left) * 2, dtype="float32")
    interleaved[0::2], interleaved[1::2] = left, right

    path = tmp_path / "stereo.wav"
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes((interleaved * 32767).astype("<i2").tobytes())

    mono, rate = audio.read_wav(path)
    assert rate == 16000
    assert len(mono) == len(left)
    assert float(np.max(np.abs(mono - (left + right) / 2))) < 1e-3


def test_resample_changes_length_and_is_a_no_op_at_the_same_rate():
    samples = _tone(seconds=1.0, rate=22050)
    downsampled = audio.resample(samples, 22050, 16000)
    assert len(downsampled) == 16000
    assert audio.resample(samples, 16000, 16000) is samples
    assert len(audio.resample(np.zeros(0, dtype="float32"), 22050, 16000)) == 0


def test_duration_and_peak_helpers():
    samples = _tone(seconds=2.0)
    assert audio.duration_seconds(samples, 16000) == pytest.approx(2.0)
    assert audio.peak_level(samples) == pytest.approx(0.5, abs=1e-3)
    assert audio.peak_level(np.zeros(0, dtype="float32")) == 0.0


def test_clipping_is_handled_on_write(tmp_path):
    loud = np.array([2.0, -2.0, 0.0], dtype="float32")
    restored, _ = audio.read_wav(audio.write_wav(loud, 16000, tmp_path / "loud.wav"))
    assert float(np.max(restored)) <= 1.0
    assert float(np.min(restored)) >= -1.0


def test_rejects_non_16_bit_files(tmp_path):
    import wave

    path = tmp_path / "8bit.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(16000)
        handle.writeframes(b"\x80" * 100)
    with pytest.raises(audio.AudioError, match="16-bit"):
        audio.read_wav(path)
