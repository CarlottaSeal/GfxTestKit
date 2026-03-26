"""
gfx_test.py - GfxTestKit: General-purpose graphics application test runner.

A config-driven test orchestrator for graphics applications.
Supports: performance benchmarking, screenshot regression (PSNR/SSIM),
and HLSL shader compilation validation.

Usage:
    python gfx_test.py --project projects/luminagi.json
    python gfx_test.py --project projects/luminagi.json --update-baseline
    python gfx_test.py --project projects/luminagi.json --test benchmark
    python gfx_test.py --project projects/luminagi.json --test shader_compile

Return codes:
    0x00  All tests passed
    0x02  Warnings (minor differences)
    0xFF  Critical failure (crash, regression, compile error)
"""

import argparse
import sys
from pathlib import Path

# Ensure the tool's root is in sys.path so `core` and `tests` are importable
TOOL_DIR = Path(__file__).parent.resolve()
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from core.config import load_config
from core.report import Report
from tests import benchmark_test, screenshot_test, shader_compile_test


def main():
    parser = argparse.ArgumentParser(
        prog="GfxTestKit",
        description="General-purpose graphics application test runner",
    )
    parser.add_argument(
        "--project", required=True,
        help="Path to project config JSON (e.g. projects/luminagi.json)",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Save current results as the new baseline",
    )
    parser.add_argument(
        "--test", type=str, default=None,
        help="Run only a specific test: benchmark, screenshot, shader_compile",
    )
    parser.add_argument(
        "--report", type=str, default=None,
        help="Save JSON report to this path",
    )
    args = parser.parse_args()

    # Load config
    try:
        cfg = load_config(args.project)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(0xFF)

    print(f"[GfxTestKit] Project: {cfg.name}")
    print(f"[GfxTestKit] Target:  {cfg.exe_path}")

    report = Report(cfg.name)
    run_filter = args.test

    # --- Benchmark ---
    if cfg.benchmark_enabled and (run_filter is None or run_filter == "benchmark"):
        print(f"\n{'='*60}")
        print(f"  [1/3] Benchmark Test")
        print(f"{'='*60}")
        result = benchmark_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Screenshot ---
    if cfg.screenshot_enabled and (run_filter is None or run_filter == "screenshot"):
        print(f"\n{'='*60}")
        print(f"  [2/3] Screenshot Regression Test")
        print(f"{'='*60}")
        result = screenshot_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Shader Compile ---
    if cfg.shader_compile_enabled and (run_filter is None or run_filter == "shader_compile"):
        print(f"\n{'='*60}")
        print(f"  [3/3] Shader Compilation Test")
        print(f"{'='*60}")
        result = shader_compile_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Report ---
    report.print_summary()

    if args.report:
        report.save_json(Path(args.report))
        print(f"[GfxTestKit] Report saved to {args.report}")

    sys.exit(report.worst_code)


if __name__ == "__main__":
    main()
