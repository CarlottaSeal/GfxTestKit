"""Unit tests for core.stats — statistical analysis module."""

import pytest
from core.stats import (
    compute_summary,
    detect_outliers_zscore,
    detect_outliers_iqr,
    detect_trend,
    detect_changepoints,
    moving_average,
    exponential_moving_average,
    analyze_series,
    format_analysis,
)


# ─── compute_summary ────────────────────────────────

class TestSummary:
    def test_empty(self):
        s = compute_summary([])
        assert s.count == 0
        assert s.mean == 0

    def test_single_value(self):
        s = compute_summary([42.0])
        assert s.count == 1
        assert s.mean == 42.0
        assert s.stdev == 0
        assert s.min == s.max == 42.0

    def test_uniform_data(self):
        data = [100.0] * 10
        s = compute_summary(data)
        assert s.mean == 100.0
        assert s.stdev == 0
        assert s.cv == 0

    def test_normal_spread(self):
        data = [100, 102, 98, 101, 99, 103, 97, 100, 101, 99]
        s = compute_summary(data)
        assert s.count == 10
        assert 99 <= s.mean <= 101
        assert s.min == 97
        assert s.max == 103
        assert s.cv < 0.1

    def test_p5_p95_with_many_points(self):
        data = list(range(1, 101))  # 1..100
        s = compute_summary([float(x) for x in data])
        assert s.p5 <= 10
        assert s.p95 >= 90


# ─── detect_outliers_zscore ──────────────────────────

class TestOutliersZscore:
    def test_no_outliers(self):
        data = [100, 101, 99, 100, 102, 98, 101]
        r = detect_outliers_zscore(data)
        assert len(r.indices) == 0

    def test_single_outlier(self):
        data = [100, 101, 99, 100, 50, 101, 99]
        r = detect_outliers_zscore(data, threshold=2.0)
        assert 4 in r.indices
        assert 50 in r.values

    def test_too_few_points(self):
        assert len(detect_outliers_zscore([1, 2]).indices) == 0

    def test_zero_variance(self):
        assert len(detect_outliers_zscore([5, 5, 5, 5]).indices) == 0

    def test_custom_threshold(self):
        data = [100, 101, 99, 100, 90, 101, 99]
        strict = detect_outliers_zscore(data, threshold=1.0)
        loose = detect_outliers_zscore(data, threshold=3.0)
        assert len(strict.indices) >= len(loose.indices)


# ─── detect_outliers_iqr ─────────────────────────────

class TestOutliersIqr:
    def test_no_outliers(self):
        data = [100, 101, 99, 100, 102, 98, 101, 99]
        r = detect_outliers_iqr(data)
        assert len(r.indices) == 0

    def test_extreme_outlier(self):
        data = [100, 101, 99, 100, 50, 101, 99, 100]
        r = detect_outliers_iqr(data)
        assert 50 in r.values

    def test_too_few_points(self):
        assert len(detect_outliers_iqr([1, 2, 3]).indices) == 0

    def test_both_directions(self):
        data = [100, 101, 99, 100, 50, 150, 101, 99]
        r = detect_outliers_iqr(data, factor=1.0)
        assert any(v < 100 for v in r.values)
        assert any(v > 100 for v in r.values)


# ─── detect_trend ────────────────────────────────────

class TestTrend:
    def test_stable(self):
        data = [100, 101, 99, 100, 101, 99, 100]
        t = detect_trend(data)
        assert t.direction == "stable"

    def test_improving(self):
        data = [100, 105, 110, 115, 120, 125, 130]
        t = detect_trend(data)
        assert t.direction == "improving"
        assert t.slope > 0
        assert t.r_squared > 0.9

    def test_degrading(self):
        data = [130, 125, 120, 115, 110, 105, 100]
        t = detect_trend(data)
        assert t.direction == "degrading"
        assert t.slope < 0

    def test_too_few_points(self):
        t = detect_trend([100, 101])
        assert t.direction == "stable"

    def test_recent_vs_overall(self):
        # Overall flat, but recent spike
        data = [100] * 10 + [120] * 5
        t = detect_trend(data, recent_window=5)
        assert t.recent_mean > t.overall_mean


# ─── detect_changepoints ────────────────────────────

class TestChangepoints:
    def test_constant_data(self):
        assert len(detect_changepoints([100.0] * 20)) == 0

    def test_sudden_drop(self):
        data = [100.0] * 10 + [80.0] * 10
        cps = detect_changepoints(data, window=5)
        assert len(cps) >= 1
        assert any(8 <= cp.index <= 12 for cp in cps)
        assert any(cp.change_pct < 0 for cp in cps)

    def test_sudden_improvement(self):
        data = [80.0] * 10 + [100.0] * 10
        cps = detect_changepoints(data, window=5)
        assert len(cps) >= 1
        assert any(cp.change_pct > 0 for cp in cps)

    def test_too_short(self):
        assert len(detect_changepoints([1, 2, 3], window=5)) == 0

    def test_merges_nearby(self):
        data = [100.0] * 10 + [80.0] * 10
        cps = detect_changepoints(data, window=3)
        # Should merge nearby detections, not return one per sliding position
        assert len(cps) <= 3


# ─── moving_average ──────────────────────────────────

class TestMovingAverage:
    def test_basic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        ma = moving_average(data, 3)
        assert len(ma) == 3
        assert ma[0] == pytest.approx(2.0)
        assert ma[2] == pytest.approx(4.0)

    def test_window_equals_length(self):
        data = [10.0, 20.0, 30.0]
        ma = moving_average(data, 3)
        assert len(ma) == 1
        assert ma[0] == pytest.approx(20.0)

    def test_window_too_large(self):
        assert moving_average([1.0, 2.0], 5) == []

    def test_empty(self):
        assert moving_average([], 3) == []


# ─── exponential_moving_average ──────────────────────

class TestEma:
    def test_basic(self):
        data = [100.0, 110.0, 105.0, 108.0]
        ema = exponential_moving_average(data, alpha=0.5)
        assert len(ema) == 4
        assert ema[0] == 100.0
        # EMA should smooth: value between raw points
        assert 100 < ema[1] < 110

    def test_alpha_zero_ignores_new(self):
        data = [100.0, 200.0, 300.0]
        ema = exponential_moving_average(data, alpha=0.0)
        assert all(v == 100.0 for v in ema)

    def test_alpha_one_tracks_raw(self):
        data = [100.0, 200.0, 300.0]
        ema = exponential_moving_average(data, alpha=1.0)
        assert ema == [100.0, 200.0, 300.0]

    def test_empty(self):
        assert exponential_moving_average([]) == []


# ─── analyze_series (integration) ────────────────────

class TestAnalyzeSeries:
    def test_full_analysis(self):
        data = [100.0] * 10 + [80.0] * 10
        a = analyze_series(data, metric="avg_fps")
        assert a.metric == "avg_fps"
        assert a.summary.count == 20
        assert a.trend.direction == "degrading"
        assert len(a.changepoints) >= 1

    def test_higher_is_not_better(self):
        # For compile time: lower is better, so increasing = degrading
        data = [10, 12, 14, 16, 18, 20, 22]
        a = analyze_series(data, metric="compile_time_ms", higher_is_better=False)
        assert a.trend.direction == "degrading"

    def test_format_does_not_crash(self):
        data = [100.0] * 10 + [80.0] * 10
        a = analyze_series(data, metric="fps")
        text = format_analysis(a)
        assert "fps" in text
        assert "Trend" in text
