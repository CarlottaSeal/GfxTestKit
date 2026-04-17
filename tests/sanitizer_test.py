"""
Runs the ASAN/UBSAN-instrumented exe, regex-matches stderr for
heap-buffer-overflow, use-after-free, integer overflow, etc.
Needs a separate build compiled with /fsanitize=address.
"""

import re
import time
from pathlib import Path

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.config import ProjectConfig
from core.runner import launch
from core.report import TestResult


# Patterns that indicate sanitizer errors in stdout/stderr
_ASAN_PATTERNS = [
    re.compile(r"ERROR:\s*AddressSanitizer:"),
    re.compile(r"heap-buffer-overflow"),
    re.compile(r"stack-buffer-overflow"),
    re.compile(r"use-after-free"),
    re.compile(r"double-free"),
    re.compile(r"alloc-dealloc-mismatch"),
    re.compile(r"heap-use-after-free"),
    re.compile(r"stack-use-after-return"),
    re.compile(r"LeakSanitizer:"),
]

_UBSAN_PATTERNS = [
    re.compile(r"runtime error:"),
    re.compile(r"undefined behavior"),
    re.compile(r"signed integer overflow"),
    re.compile(r"null pointer passed"),
    re.compile(r"misaligned address"),
    re.compile(r"shift exponent"),
    re.compile(r"division by zero"),
]


def _parse_sanitizer_output(output: str) -> tuple[int, list[str]]:
    """
    Scan output for ASAN/UBSAN error reports.
    Returns (error_count, list of matching lines).
    """
    errors = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        for pattern in _ASAN_PATTERNS + _UBSAN_PATTERNS:
            if pattern.search(line):
                errors.append(line)
                break
    return len(errors), errors


def _extract_summary(output: str) -> str:
    """Extract the ASAN summary line if present."""
    for line in output.split("\n"):
        if "SUMMARY:" in line:
            return line.strip()
    return ""


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Run the application with sanitizer-enabled build and check for errors.
    """
    start = time.time()

    if not cfg.sanitizer_exe:
        return TestResult(
            name="sanitizer", status="SKIP", return_code=RET_SUCCESS,
            message="No sanitizer build configured (set sanitizer.exe_path)",
            duration_seconds=time.time() - start,
        )

    exe = Path(cfg.sanitizer_exe)
    if not exe.exists():
        return TestResult(
            name="sanitizer", status="SKIP", return_code=RET_WARNING,
            message=f"Sanitizer build not found: {exe}",
            duration_seconds=time.time() - start,
        )

    print(f"  [Sanitizer] Running: {exe.name}")
    print(f"  [Sanitizer] Type: {cfg.sanitizer_type}")

    # Set sanitizer-specific env vars
    env = dict(cfg.env_vars) if cfg.env_vars else {}

    # ASAN options: halt on error, print full stack, detect leaks
    if "ASAN_OPTIONS" not in env:
        env["ASAN_OPTIONS"] = "halt_on_error=0:print_stacktrace=1:detect_leaks=1"
    if "UBSAN_OPTIONS" not in env:
        env["UBSAN_OPTIONS"] = "halt_on_error=0:print_stacktrace=1"

    run_result = launch(
        exe_path=exe,
        args=cfg.sanitizer_args,
        working_dir=Path(cfg.working_dir) if cfg.working_dir else None,
        timeout=cfg.timeout,
        env=env,
    )

    # Crashed is expected with ASAN on severe errors — still parse output
    combined = run_result.stdout + run_result.stderr
    error_count, error_lines = _parse_sanitizer_output(combined)
    summary = _extract_summary(combined)

    if error_count > 0:
        print(f"  [Sanitizer] Found {error_count} error(s):")
        for line in error_lines[:10]:
            print(f"           {line}")
        if summary:
            print(f"  [Sanitizer] {summary}")

        return TestResult(
            name="sanitizer", status="FAIL", return_code=RET_CRITICAL,
            message=f"{error_count} sanitizer error(s) detected",
            details={
                "error_count": error_count,
                "type": cfg.sanitizer_type,
                "summary": summary,
                "errors": error_lines[:20],
            },
            duration_seconds=time.time() - start,
        )

    if run_result.crashed:
        return TestResult(
            name="sanitizer", status="FAIL", return_code=RET_CRITICAL,
            message=f"Crashed under sanitizer: {run_result.crash_reason}",
            duration_seconds=time.time() - start,
        )

    print(f"  [Sanitizer] Clean — no errors detected")
    return TestResult(
        name="sanitizer", status="PASS",
        message=f"No sanitizer errors ({cfg.sanitizer_type})",
        duration_seconds=time.time() - start,
    )
