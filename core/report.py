"""
report.py - Test result aggregation and severity-graded reporting.

Return code convention (matches The-Forge PyBuild.py):
  0x00 = all clear
  0x02 = warnings (minor screenshot diff, small perf change)
  0xFF = critical (crash, major regression, compilation failure)
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    status: str = "PASS"       # PASS / WARNING / FAIL / SKIP
    return_code: int = RET_SUCCESS
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


class Report:
    """Collects test results and produces summary."""

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.results: list[TestResult] = []
        self.start_time = time.time()

    def add(self, result: TestResult):
        self.results.append(result)

    @property
    def worst_code(self) -> int:
        if not self.results:
            return RET_SUCCESS
        return max(r.return_code for r in self.results)

    @property
    def overall_status(self) -> str:
        code = self.worst_code
        if code == RET_SUCCESS:
            return "PASS"
        elif code <= RET_WARNING:
            return "WARNING"
        return "FAIL"

    def print_summary(self):
        duration = time.time() - self.start_time
        w = 60

        print(f"\n{'=' * w}")
        print(f"  TEST REPORT: {self.project_name}")
        print(f"{'=' * w}")

        for r in self.results:
            icon = {"PASS": "+", "WARNING": "~", "FAIL": "!", "SKIP": "-"}.get(r.status, "?")
            print(f"  [{icon}] {r.name:<30} {r.status:<10} {r.duration_seconds:.1f}s")
            if r.message:
                print(f"      {r.message}")

        print(f"{'=' * w}")
        print(f"  Total: {len(self.results)} tests in {duration:.1f}s")
        print(f"  Result: {self.overall_status} (exit code 0x{self.worst_code:02X})")
        print(f"{'=' * w}\n")

    def save_json(self, path: Path):
        """Save structured results for CI consumption."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project": self.project_name,
            "overall": self.overall_status,
            "return_code": self.worst_code,
            "duration_seconds": round(time.time() - self.start_time, 2),
            "tests": [
                {
                    "name": r.name,
                    "status": r.status,
                    "return_code": r.return_code,
                    "message": r.message,
                    "duration_seconds": round(r.duration_seconds, 2),
                    "details": r.details,
                }
                for r in self.results
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
