"""
benchmark_test.py - Performance regression detection.

Launches the target application in benchmark mode, parses the FPS metrics JSON,
and compares against a stored baseline. Reports regressions using configurable
per-metric percentage thresholds.

Inspired by The-Forge's FSL analysis baseline comparison system.
"""

import json
import time
from pathlib import Path

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.config import ProjectConfig
from core.runner import launch, RunResult
from core.report import TestResult


def _load_metrics(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def _save_metrics(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


BASELINE_RUNS = 3  # Number of runs when establishing baseline; take median


def _run_once(cfg: ProjectConfig) -> dict | None:
    """Launch the app once in benchmark mode, return metrics dict or None on failure."""
    result_path = Path(cfg.benchmark_result_file)
    if result_path.exists():
        result_path.unlink()

    # Inject --warmup if configured and not already in args
    args = list(cfg.benchmark_args)
    if "--warmup" not in args and cfg.benchmark_warmup_frames != 60:
        args.extend(["--warmup", str(cfg.benchmark_warmup_frames)])

    run_result = launch(
        exe_path=Path(cfg.exe_path),
        args=args,
        working_dir=Path(cfg.working_dir) if cfg.working_dir else None,
        timeout=cfg.timeout,
        env=cfg.env_vars or None,
    )

    if run_result.crashed or run_result.timed_out:
        return None

    return _load_metrics(result_path)


def _median_metrics(runs: list[dict]) -> dict:
    """Given multiple run results, return the one with the median avg_fps."""
    runs.sort(key=lambda r: r.get("avg_fps", 0))
    median = runs[len(runs) // 2]
    return {k: v for k, v in median.items() if k != "per_frame_fps"}


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Execute the benchmark test.

    1. Launch app with benchmark args (multiple runs for baseline)
    2. Read result JSON
    3. Compare against baseline
    4. Return TestResult with regression info
    """
    start = time.time()
    result_path = Path(cfg.benchmark_result_file)
    baseline_path = Path(cfg.benchmark_baseline_file)

    if update_baseline:
        # Run multiple times, take median to reduce noise
        print(f"  [Benchmark] Running {BASELINE_RUNS}x for stable baseline...")
        all_runs = []
        for i in range(BASELINE_RUNS):
            print(f"  [Benchmark] Run {i + 1}/{BASELINE_RUNS}")
            metrics = _run_once(cfg)
            if metrics is None:
                return TestResult(
                    name="benchmark",
                    status="FAIL",
                    return_code=RET_CRITICAL,
                    message=f"Application failed on baseline run {i + 1}",
                    duration_seconds=time.time() - start,
                )
            print(f"  [Benchmark]   avg_fps={metrics.get('avg_fps', 0):.1f}")
            all_runs.append(metrics)

        baseline_data = _median_metrics(all_runs)
        _save_metrics(baseline_data, baseline_path)
        all_avg = [r.get("avg_fps", 0) for r in all_runs]
        return TestResult(
            name="benchmark",
            status="PASS",
            message=f"Baseline saved (median of {BASELINE_RUNS} runs): avg_fps={baseline_data.get('avg_fps', 0):.1f}  [all: {', '.join(f'{a:.1f}' for a in all_avg)}]",
            details=baseline_data,
            duration_seconds=time.time() - start,
        )

    # Multiple runs for comparison too (same stability as baseline)
    COMPARE_RUNS = 3
    print(f"  [Benchmark] Running {COMPARE_RUNS}x for stable comparison...")
    all_runs = []
    for i in range(COMPARE_RUNS):
        print(f"  [Benchmark] Run {i + 1}/{COMPARE_RUNS}")
        m = _run_once(cfg)
        if m is None:
            return TestResult(
                name="benchmark",
                status="FAIL",
                return_code=RET_CRITICAL,
                message=f"Application failed on comparison run {i + 1}",
                duration_seconds=time.time() - start,
            )
        print(f"  [Benchmark]   avg_fps={m.get('avg_fps', 0):.1f}")
        all_runs.append(m)
    metrics = _median_metrics(all_runs)

    # Load baseline
    baseline = _load_metrics(baseline_path)
    if baseline is None:
        # No baseline yet — save current as initial baseline
        baseline_data = {k: v for k, v in metrics.items() if k != "per_frame_fps"}
        _save_metrics(baseline_data, baseline_path)
        return TestResult(
            name="benchmark",
            status="PASS",
            message=f"Initial baseline created: avg_fps={metrics.get('avg_fps', 0):.1f}",
            details=metrics,
            duration_seconds=time.time() - start,
        )

    # Compare metrics
    thresholds = cfg.benchmark_thresholds
    ret_code = RET_SUCCESS
    comparisons = {}

    check_metrics = [
        ("avg_fps", thresholds.get("avg_fps_pct", 10.0)),
        ("p1_fps",  thresholds.get("p1_fps_pct", 15.0)),
        ("p5_fps",  thresholds.get("p5_fps_pct", 15.0)),
        ("min_fps", thresholds.get("min_fps_pct", 20.0)),
    ]

    regression_msgs = []

    print(f"\n  {'Metric':>10}  {'Current':>10}  {'Baseline':>10}  {'Delta':>10}  Status")
    print(f"  {'-'*56}")

    for metric_name, threshold in check_metrics:
        cur = metrics.get(metric_name, 0.0)
        base = baseline.get(metric_name, 0.0)

        if base <= 0:
            delta_pct = 0.0
            status = "N/A"
        else:
            delta_pct = ((cur - base) / base) * 100.0
            if delta_pct < -threshold:
                status = "REGRESS"
                ret_code = max(ret_code, RET_CRITICAL)
                regression_msgs.append(f"{metric_name}: {delta_pct:+.1f}%")
            elif delta_pct < -(threshold * 0.5):
                status = "WARN"
                ret_code = max(ret_code, RET_WARNING)
            else:
                status = "OK"

        comparisons[metric_name] = {
            "current": cur, "baseline": base,
            "delta_pct": round(delta_pct, 2), "status": status,
        }
        print(f"  {metric_name:>10}  {cur:10.1f}  {base:10.1f}  {delta_pct:+9.1f}%  {status}")

    # Build result
    if ret_code == RET_SUCCESS:
        msg = f"No regression (avg_fps={metrics.get('avg_fps', 0):.1f})"
        status_str = "PASS"
    elif ret_code == RET_WARNING:
        msg = "Minor performance change detected"
        status_str = "WARNING"
    else:
        msg = "Regression: " + ", ".join(regression_msgs)
        status_str = "FAIL"

    return TestResult(
        name="benchmark",
        status=status_str,
        return_code=ret_code,
        message=msg,
        details=comparisons,
        duration_seconds=time.time() - start,
    )
