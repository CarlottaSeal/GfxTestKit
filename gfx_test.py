"""
Entry point.  Reads a project JSON, runs whichever tests are enabled,
prints the report, exits with the worst return code.

    python gfx_test.py --project projects/luminagi.json
    python gfx_test.py --project projects/luminagi.json --test benchmark
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
from tests import build_test, benchmark_test, screenshot_test, shader_compile_test, memleak_test, sanitizer_test


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
        help="Run only a specific test: build, benchmark, screenshot, shader_compile, memleak, sanitizer",
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
    step = 0
    total = sum([cfg.build_enabled, cfg.benchmark_enabled, cfg.screenshot_enabled,
                 cfg.shader_compile_enabled, cfg.memleak_enabled, cfg.sanitizer_enabled])

    # --- Build (always first) ---
    if cfg.build_enabled and (run_filter is None or run_filter == "build"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Build")
        print(f"{'='*60}")
        result = build_test.run(cfg)
        report.add(result)
        if result.return_code >= 0xFF and run_filter is None:
            print("  [GfxTestKit] Build failed — skipping remaining tests")
            report.print_summary()
            if args.report:
                report.save_json(Path(args.report))
            sys.exit(report.worst_code)

    # --- Benchmark ---
    if cfg.benchmark_enabled and (run_filter is None or run_filter == "benchmark"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Benchmark Test")
        print(f"{'='*60}")
        result = benchmark_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Screenshot ---
    if cfg.screenshot_enabled and (run_filter is None or run_filter == "screenshot"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Screenshot Regression Test")
        print(f"{'='*60}")
        result = screenshot_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Shader Compile ---
    if cfg.shader_compile_enabled and (run_filter is None or run_filter == "shader_compile"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Shader Compilation Test")
        print(f"{'='*60}")
        result = shader_compile_test.run(cfg, update_baseline=args.update_baseline)
        report.add(result)

    # --- Memory Leak ---
    if cfg.memleak_enabled and (run_filter is None or run_filter == "memleak"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Memory Leak Detection")
        print(f"{'='*60}")
        result = memleak_test.run(cfg)
        report.add(result)

    # --- Sanitizer ---
    if cfg.sanitizer_enabled and (run_filter is None or run_filter == "sanitizer"):
        step += 1
        print(f"\n{'='*60}")
        print(f"  [{step}/{total}] Sanitizer ({cfg.sanitizer_type.upper()})")
        print(f"{'='*60}")
        result = sanitizer_test.run(cfg)
        report.add(result)

    # --- Report ---
    report.print_summary()

    if args.report:
        report.save_json(Path(args.report))
        print(f"[GfxTestKit] Report saved to {args.report}")

    sys.exit(report.worst_code)


if __name__ == "__main__":
    main()
