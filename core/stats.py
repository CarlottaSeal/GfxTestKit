"""
stats.py - Statistical analysis for performance time series.

Outlier detection, trend analysis, and changepoint detection for
tracking performance metrics across CI runs. stdlib only (no numpy).
"""

from dataclasses import dataclass, field
from math import sqrt
from statistics import mean, median, stdev, quantiles



@dataclass(frozen=True)
class SummaryStats:
    count: int
    mean: float
    median: float
    stdev: float
    cv: float  # coefficient of variation
    p5: float
    p95: float
    min: float
    max: float


@dataclass(frozen=True)
class OutlierResult:
    indices: list[int]
    values: list[float]
    method: str
    threshold: float


@dataclass(frozen=True)
class TrendResult:
    direction: str  # "improving" | "degrading" | "stable"
    slope: float
    r_squared: float
    recent_mean: float
    overall_mean: float
    change_pct: float


@dataclass(frozen=True)
class Changepoint:
    index: int
    before_mean: float
    after_mean: float
    change_pct: float
    significance: float  # Welch's t-statistic


@dataclass(frozen=True)
class SeriesAnalysis:
    metric: str
    summary: SummaryStats
    outliers_zscore: OutlierResult
    outliers_iqr: OutlierResult
    trend: TrendResult
    changepoints: list[Changepoint]



def compute_summary(data: list[float]) -> SummaryStats:
    """Descriptive statistics for a numeric series."""
    n = len(data)
    if n == 0:
        return SummaryStats(0, 0, 0, 0, 0, 0, 0, 0, 0)
    if n == 1:
        v = data[0]
        return SummaryStats(1, v, v, 0, 0, v, v, v, v)

    m = mean(data)
    med = median(data)
    sd = stdev(data)
    cv = sd / abs(m) if m != 0 else 0

    if n >= 20:
        q = quantiles(data, n=20)
        p5, p95 = q[0], q[-1]
    else:
        s = sorted(data)
        p5 = s[max(0, int(n * 0.05))]
        p95 = s[min(n - 1, int(n * 0.95))]

    return SummaryStats(
        count=n,
        mean=round(m, 2),
        median=round(med, 2),
        stdev=round(sd, 2),
        cv=round(cv, 4),
        p5=round(p5, 2),
        p95=round(p95, 2),
        min=round(min(data), 2),
        max=round(max(data), 2),
    )



def detect_outliers_zscore(
    data: list[float], threshold: float = 2.0
) -> OutlierResult:
    """Flag points beyond `threshold` standard deviations from mean."""
    if len(data) < 3:
        return OutlierResult([], [], "zscore", threshold)

    m = mean(data)
    sd = stdev(data)
    if sd == 0:
        return OutlierResult([], [], "zscore", threshold)

    indices, values = [], []
    for i, v in enumerate(data):
        if abs(v - m) / sd > threshold:
            indices.append(i)
            values.append(v)

    return OutlierResult(indices, values, "zscore", threshold)


def detect_outliers_iqr(
    data: list[float], factor: float = 1.5
) -> OutlierResult:
    """IQR fences method. More robust to skew than Z-score."""
    if len(data) < 4:
        return OutlierResult([], [], "iqr", factor)

    q = quantiles(data, n=4)  # [Q1, Q2, Q3]
    q1, q3 = q[0], q[2]
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr

    indices, values = [], []
    for i, v in enumerate(data):
        if v < lower or v > upper:
            indices.append(i)
            values.append(v)

    return OutlierResult(indices, values, "iqr", factor)



def detect_trend(
    data: list[float], recent_window: int = 5
) -> TrendResult:
    """OLS slope + recent window vs overall mean."""
    n = len(data)
    if n < 3:
        m = mean(data) if data else 0
        return TrendResult("stable", 0.0, 0.0, m, m, 0.0)

    x_mean = (n - 1) / 2.0
    y_mean = mean(data)

    ss_xy = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(data))
    ss_xx = sum((i - x_mean) ** 2 for i in range(n))

    slope = ss_xy / ss_xx if ss_xx != 0 else 0
    intercept = y_mean - slope * x_mean

    ss_res = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(data))
    ss_tot = sum((v - y_mean) ** 2 for v in data)
    r_sq = max(0, 1 - ss_res / ss_tot) if ss_tot != 0 else 0

    recent = data[-min(recent_window, n) :]
    recent_m = mean(recent)
    change = ((recent_m - y_mean) / abs(y_mean) * 100) if y_mean != 0 else 0

    if abs(change) < 2.0:
        direction = "stable"
    elif slope > 0:
        direction = "improving"
    else:
        direction = "degrading"

    return TrendResult(
        direction=direction,
        slope=round(slope, 4),
        r_squared=round(r_sq, 4),
        recent_mean=round(recent_m, 2),
        overall_mean=round(y_mean, 2),
        change_pct=round(change, 2),
    )



def detect_changepoints(
    data: list[float], window: int = 5, threshold: float = 2.0
) -> list[Changepoint]:
    """Sliding-window Welch's t-test for sudden shifts."""
    n = len(data)
    if n < 2 * window:
        return []

    candidates = []
    for i in range(window, n - window + 1):
        before = data[i - window : i]
        after = data[i : i + window]

        m1, m2 = mean(before), mean(after)
        s1 = stdev(before) if len(before) > 1 else 0.001
        s2 = stdev(after) if len(after) > 1 else 0.001

        se = sqrt(s1**2 / len(before) + s2**2 / len(after))
        if se == 0:
            continue

        t_stat = abs(m1 - m2) / se
        if t_stat > threshold:
            change_pct = ((m2 - m1) / abs(m1) * 100) if m1 != 0 else 0
            candidates.append(
                Changepoint(
                    index=i,
                    before_mean=round(m1, 2),
                    after_mean=round(m2, 2),
                    change_pct=round(change_pct, 2),
                    significance=round(t_stat, 2),
                )
            )

    # Keep most significant detection per cluster
    if not candidates:
        return []

    merged = [candidates[0]]
    for cp in candidates[1:]:
        if cp.index - merged[-1].index < window:
            if cp.significance > merged[-1].significance:
                merged[-1] = cp
        else:
            merged.append(cp)

    return merged



def moving_average(data: list[float], window: int) -> list[float]:
    """Simple moving average."""
    if len(data) < window or window < 1:
        return []
    return [mean(data[i : i + window]) for i in range(len(data) - window + 1)]


def exponential_moving_average(data: list[float], alpha: float = 0.3) -> list[float]:
    """EMA. alpha in [0,1]: higher = more weight on recent."""
    if not data:
        return []
    result = [data[0]]
    for v in data[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return [round(v, 2) for v in result]



def analyze_series(
    data: list[float],
    metric: str = "value",
    higher_is_better: bool = True,
    zscore_threshold: float = 2.0,
    iqr_factor: float = 1.5,
    trend_window: int = 5,
    changepoint_window: int = 5,
    changepoint_threshold: float = 2.0,
) -> SeriesAnalysis:
    """Run all analyses on a time series and bundle the results."""
    trend = detect_trend(data, trend_window)

    # Flip direction for metrics where lower is better (e.g. compile time)
    if not higher_is_better and trend.direction != "stable":
        flipped = "improving" if trend.direction == "degrading" else "degrading"
        trend = TrendResult(
            direction=flipped,
            slope=trend.slope,
            r_squared=trend.r_squared,
            recent_mean=trend.recent_mean,
            overall_mean=trend.overall_mean,
            change_pct=trend.change_pct,
        )

    return SeriesAnalysis(
        metric=metric,
        summary=compute_summary(data),
        outliers_zscore=detect_outliers_zscore(data, zscore_threshold),
        outliers_iqr=detect_outliers_iqr(data, iqr_factor),
        trend=trend,
        changepoints=detect_changepoints(data, changepoint_window, changepoint_threshold),
    )


def format_analysis(analysis: SeriesAnalysis) -> str:
    """One-line-per-finding console summary."""
    lines = [f"  [{analysis.metric}] {analysis.summary.count} data points"]
    s = analysis.summary
    lines.append(
        f"    Mean={s.mean}  Median={s.median}  Stdev={s.stdev}  "
        f"CV={s.cv:.2%}  Range=[{s.min}, {s.max}]"
    )

    t = analysis.trend
    lines.append(
        f"    Trend: {t.direction} (slope={t.slope}, R²={t.r_squared}, "
        f"recent={t.recent_mean} vs overall={t.overall_mean}, {t.change_pct:+.1f}%)"
    )

    oz = analysis.outliers_zscore
    if oz.indices:
        lines.append(f"    Outliers (Z-score): {len(oz.indices)} at indices {oz.indices}")
    oi = analysis.outliers_iqr
    if oi.indices:
        lines.append(f"    Outliers (IQR):     {len(oi.indices)} at indices {oi.indices}")

    for cp in analysis.changepoints:
        lines.append(
            f"    Changepoint at #{cp.index}: "
            f"{cp.before_mean} → {cp.after_mean} ({cp.change_pct:+.1f}%, t={cp.significance})"
        )

    return "\n".join(lines)
