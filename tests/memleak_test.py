"""
memleak_test.py - Memory leak detection.

Parses memory leak reports from the application's output or log files.
Supports two modes:
  1. Parse a .memleaks file (The-Forge convention)
  2. Scan stdout/stderr for CRT debug leak reports (MSVC _CrtDumpMemoryLeaks)

Any leak detected = critical failure (0xFF), same as The-Forge's FindMemoryLeaks().
"""

import re
import time
from pathlib import Path

from core import RET_SUCCESS, RET_CRITICAL
from core.config import ProjectConfig
from core.runner import launch
from core.report import TestResult


def _parse_memleaks_file(path: Path) -> tuple[int, list[str]]:
    """
    Parse a .memleaks file. The-Forge format:
    First line: "N memory leak(s) found:"
    Followed by leak details.
    Returns (leak_count, detail_lines).
    """
    if not path.exists():
        return 0, []

    with open(path, "r", errors="replace") as f:
        content = f.read()

    # The-Forge regex: "N memory leak(s) found:"
    match = re.search(r"(\d+)\s+memory\s+leaks?\s+found", content)
    if match:
        count = int(match.group(1))
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return count, lines

    return 0, []


def _parse_crt_leaks(output: str) -> tuple[int, list[str]]:
    """
    Parse MSVC CRT memory leak output from stdout/stderr.
    Looks for: "Detected memory leaks!" and "{NNN} normal block" patterns.
    """
    if "Detected memory leaks!" not in output:
        return 0, []

    leak_lines = []
    leak_count = 0
    for line in output.split("\n"):
        line = line.strip()
        # "{123} normal block at 0x00AB1234, 64 bytes long."
        if re.match(r"\{\d+\}\s+(normal|client)\s+block", line):
            leak_count += 1
            leak_lines.append(line)

    # If we found the header but no specific blocks, count as 1
    if leak_count == 0:
        leak_count = 1
        leak_lines.append("Detected memory leaks! (details not parsed)")

    return leak_count, leak_lines


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Run the application and check for memory leaks.

    Note: update_baseline is unused — memleak has no baseline concept.
    The parameter exists so every module shares the same run() signature.
    Launches a Debug build (which has CRT leak detection enabled) or
    checks for .memleaks file output.
    """
    start = time.time()

    # Launch application
    run_result = launch(
        exe_path=Path(cfg.exe_path),
        args=cfg.memleak_args,
        working_dir=Path(cfg.working_dir) if cfg.working_dir else None,
        timeout=cfg.timeout,
        env=cfg.env_vars or None,
    )

    if run_result.crashed:
        return TestResult(
            name="memleak", status="FAIL", return_code=RET_CRITICAL,
            message=f"Application crashed: {run_result.crash_reason}",
            duration_seconds=time.time() - start,
        )

    total_leaks = 0
    all_details = []

    # Check .memleaks file if configured
    if cfg.memleak_file:
        file_path = Path(cfg.memleak_file)
        count, details = _parse_memleaks_file(file_path)
        total_leaks += count
        all_details.extend(details)
        if count > 0:
            print(f"  [MemLeak] {file_path.name}: {count} leak(s)")

    # Check stdout/stderr for CRT leak reports
    combined_output = run_result.stdout + run_result.stderr
    count, details = _parse_crt_leaks(combined_output)
    total_leaks += count
    all_details.extend(details)
    if count > 0:
        print(f"  [MemLeak] CRT output: {count} leak(s)")
        for line in details[:5]:
            print(f"           {line}")

    if total_leaks > 0:
        return TestResult(
            name="memleak", status="FAIL", return_code=RET_CRITICAL,
            message=f"{total_leaks} memory leak(s) detected",
            details={"leak_count": total_leaks, "lines": all_details[:20]},
            duration_seconds=time.time() - start,
        )

    print(f"  [MemLeak] No leaks detected")
    return TestResult(
        name="memleak", status="PASS",
        message="No memory leaks detected",
        duration_seconds=time.time() - start,
    )
