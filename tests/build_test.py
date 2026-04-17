"""Compiles the .sln via MSBuild (found through vswhere). Fails fast so later tests don't run against a broken binary."""

import subprocess
import time
import re
from pathlib import Path

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.config import ProjectConfig
from core.report import TestResult


def _find_msbuild() -> str | None:
    """Locate MSBuild.exe via vswhere (standard VS discovery)."""
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if not vswhere.exists():
        return None

    try:
        result = subprocess.run(
            [str(vswhere), "-latest", "-requires", "Microsoft.Component.MSBuild",
             "-find", r"MSBuild\**\Bin\MSBuild.exe"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        if lines and Path(lines[0]).exists():
            return lines[0]
    except Exception:
        pass
    return None


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Build the project solution with MSBuild.
    """
    start = time.time()

    sln_path = Path(cfg.build_solution)
    if not sln_path.exists():
        return TestResult(
            name="build", status="FAIL", return_code=RET_CRITICAL,
            message=f"Solution not found: {sln_path}",
            duration_seconds=time.time() - start,
        )

    # Find MSBuild
    msbuild = cfg.build_msbuild_path
    if not msbuild:
        msbuild = _find_msbuild()
    if not msbuild:
        return TestResult(
            name="build", status="FAIL", return_code=RET_CRITICAL,
            message="MSBuild.exe not found. Install Visual Studio or set build.msbuild_path in config.",
            duration_seconds=time.time() - start,
        )

    config = cfg.build_configuration
    platform = cfg.build_platform

    cmd = [
        msbuild,
        str(sln_path),
        f"/p:Configuration={config}",
        f"/p:Platform={platform}",
        "/m",          # parallel build
        "/nologo",
        "/verbosity:minimal",
    ]

    print(f"  [Build] MSBuild: {Path(msbuild).name}")
    print(f"  [Build] Solution: {sln_path.name}")
    print(f"  [Build] Config: {config}|{platform}")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=cfg.build_timeout,
        )
        output = proc.stdout + proc.stderr

        # Count errors and warnings from MSBuild output
        error_count = len(re.findall(r": error ", output))
        warning_count = len(re.findall(r": warning ", output))

        if proc.returncode != 0 or error_count > 0:
            # Print last error lines
            error_lines = [l for l in output.split("\n") if ": error " in l]
            for line in error_lines[:5]:
                print(f"  [Build] {line.strip()}")

            return TestResult(
                name="build", status="FAIL", return_code=RET_CRITICAL,
                message=f"Build failed: {error_count} errors, {warning_count} warnings",
                details={"errors": error_count, "warnings": warning_count},
                duration_seconds=time.time() - start,
            )

        warn_str = f" ({warning_count} warnings)" if warning_count > 0 else ""
        print(f"  [Build] Succeeded{warn_str}")

        return TestResult(
            name="build", status="PASS",
            message=f"Build succeeded{warn_str}",
            details={"errors": 0, "warnings": warning_count},
            duration_seconds=time.time() - start,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            name="build", status="FAIL", return_code=RET_CRITICAL,
            message=f"Build timed out after {cfg.build_timeout}s",
            duration_seconds=time.time() - start,
        )
    except FileNotFoundError:
        return TestResult(
            name="build", status="FAIL", return_code=RET_CRITICAL,
            message=f"MSBuild not found at: {msbuild}",
            duration_seconds=time.time() - start,
        )
