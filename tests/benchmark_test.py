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


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Execute the benchmark test.

    1. Launch app with benchmark args
    2. Read result JSON
    3. Compare against baseline
    4. Return TestResult with regression info
    """
    start = time.time()
    result_path = Path(cfg.benchmark_result_file)
    baseline_path = Path(cfg.benchmark_baseline_file)

    # Clean previous results
    if result_path.exists():
        result_path.unlink()

    # Launch application
    run_result = launch(
        exe_path=Path(cfg.exe_path),
        args=cfg.benchmark_args,
        working_dir=Path(cfg.working_dir) if cfg.working_dir else None,
        timeout=cfg.timeout,
        env=cfg.env_vars or None,
    )

    if run_result.crashed:
        return TestResult(
            name="benchmark",
            status="FAIL",
            return_code=RET_CRITICAL,
            message=f"Application crashed: {run_result.crash_reason}",
            duration_seconds=time.time() - start,
        )

    if run_result.timed_out:
        return TestResult(
            name="benchmark",
            status="FAIL",
            return_code=RET_CRITICAL,
            message=f"Application timed out after {cfg.timeout}s",
            duration_seconds=time.time() - start,
        )

    # Read results
    metrics = _load_metrics(result_path)
    if metrics is None:
        return TestResult(
            name="benchmark",
            status="FAIL",
            return_code=RET_CRITICAL,
            message=f"Result file not found: {result_path}",
            duration_seconds=time.time() - start,
        )

    # Update baseline mode
    if update_baseline:
        # Strip per-frame data for cleaner baseline
        baseline_data = {k: v for k, v in metrics.items() if k != "per_frame_fps"}
        _save_metrics(baseline_data, baseline_path)
        return TestResult(
            name="benchmark",
            status="PASS",
            message=f"Baseline saved: avg_fps={metrics.get('avg_fps', 0):.1f}",
            details=metrics,
            duration_seconds=time.time() - start,
        )

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
