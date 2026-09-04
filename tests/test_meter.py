import pytest

from mumbles.meter import (CEILING_DB, FLOOR_DB, LEVELS, LevelMeter,
                           render_bar, rms_to_unit)


def test_silence_and_overload_clamp():
    assert rms_to_unit(0.0) == 0.0
    assert rms_to_unit(-1.0) == 0.0
    assert rms_to_unit(float("nan")) == 0.0
    assert rms_to_unit(1.0) == 1.0
    assert rms_to_unit(10.0) == 1.0


def test_decibel_scale_endpoints_and_midpoint():
    floor_rms = 10 ** (FLOOR_DB / 20.0)
    ceiling_rms = 10 ** (CEILING_DB / 20.0)
    mid_rms = 10 ** (((FLOOR_DB + CEILING_DB) / 2) / 20.0)
    assert rms_to_unit(floor_rms) == pytest.approx(0.0, abs=1e-6)
    assert rms_to_unit(ceiling_rms) == pytest.approx(1.0, abs=1e-6)
    assert rms_to_unit(mid_rms) == pytest.approx(0.5, abs=1e-6)


def test_scale_is_monotonic():
    values = [rms_to_unit(rms) for rms in (0.0005, 0.005, 0.02, 0.08, 0.3, 0.9)]
    assert values == sorted(values)


def test_bar_width_is_constant_at_every_level():
    widths = {len(render_bar(level / 20.0)) for level in range(21)}
    assert widths == {6}
    assert len(render_bar(0.5, width=12)) == 12


def test_bar_endpoints_and_clamping():
    assert render_bar(0.0) == LEVELS[0] * 6
    assert render_bar(1.0) == LEVELS[-1] * 6
    assert render_bar(-5.0) == render_bar(0.0)
    assert render_bar(5.0) == render_bar(1.0)


def test_bar_fills_from_the_left():
    bar = render_bar(0.5)
    assert bar[:3] == LEVELS[-1] * 3
    assert bar[3:] == LEVELS[0] * 3


def test_meter_reports_the_loudest_value_between_frames():
    meter = LevelMeter()
    meter.push(0.001)
    meter.push(0.2)      # a brief peak must not be missed
    meter.push(0.001)
    assert meter.sample() == pytest.approx(rms_to_unit(0.2))


def test_meter_decays_toward_silence_and_settles_at_zero():
    meter = LevelMeter(decay=0.5)
    meter.push(0.5)
    first = meter.sample()
    assert first > 0.5
    previous = first
    for _ in range(12):
        current = meter.sample()
        assert current < previous or current == 0.0
        previous = current
    assert meter.level == 0.0
    assert meter.render() == LEVELS[0] * 6


def test_a_new_peak_beats_the_decaying_level():
    meter = LevelMeter(decay=0.5)
    meter.push(0.5)
    meter.sample()
    meter.sample()
    meter.push(0.5)
    assert meter.sample() == pytest.approx(rms_to_unit(0.5))


def test_reset_clears_pending_peaks_too():
    meter = LevelMeter()
    meter.push(0.5)
    meter.reset()
    assert meter.level == 0.0
    assert meter.sample() == 0.0
