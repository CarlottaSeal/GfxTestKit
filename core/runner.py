"""
runner.py - Process lifecycle management for graphics applications.

Launches a target executable, monitors for crashes and timeouts,
and captures exit codes. Handles Windows-specific crash codes
(access violation, stack overflow, etc.).
"""

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from core import RET_SUCCESS, RET_TIMEOUT, RET_CRITICAL


# Windows NT exception codes commonly seen in graphics app crashes
_CRASH_CODES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0x80000003: "BREAKPOINT",
}


@dataclass
class RunResult:
    """Outcome of a single application execution."""
    return_code: int = RET_SUCCESS
    duration_seconds: float = 0.0
    timed_out: bool = False
    crash_reason: str = ""
    stdout: str = ""
    stderr: str = ""

    @property
    def crashed(self) -> bool:
        return self.crash_reason != ""

    @property
    def passed(self) -> bool:
        return self.return_code == 0 and not self.crashed and not self.timed_out


def launch(
    exe_path: Path,
    args: list[str] | None = None,
    working_dir: Path | None = None,
    timeout: int = 120,
    env: dict | None = None,
) -> RunResult:
    """
    Launch a graphics application and wait for it to exit.

    Args:
        exe_path:    Absolute path to executable.
        args:        Command-line arguments to pass.
        working_dir: Working directory (defaults to exe's parent).
        timeout:     Seconds before force-kill.
        env:         Extra environment variables to inject.

    Returns:
        RunResult describing how the run went.
    """
    exe_path = Path(exe_path).resolve()
    if not exe_path.exists():
        print(f"  [Runner] ERROR: executable not found: {exe_path}")
        return RunResult(return_code=RET_CRITICAL, crash_reason="EXE_NOT_FOUND")

    if working_dir is None:
        working_dir = exe_path.parent
    working_dir = Path(working_dir).resolve()

    cmd = [str(exe_path)]
    if args:
        cmd.extend(args)

    # Merge env
    run_env = None
    if env:
        import os
        run_env = os.environ.copy()
        run_env.update(env)

    print(f"  [Runner] Launch: {exe_path.name} {' '.join(args or [])}")
    print(f"  [Runner] CWD:    {working_dir}")

    result = RunResult()
    start = time.time()

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=run_env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        try:
            out, err = proc.communicate(timeout=timeout)
            result.stdout = out.decode("utf-8", errors="replace")
            result.stderr = err.decode("utf-8", errors="replace")
            result.return_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            result.timed_out = True
            result.return_code = RET_TIMEOUT

    except OSError as e:
        result.return_code = RET_CRITICAL
        result.crash_reason = f"OS_ERROR: {e}"

    result.duration_seconds = time.time() - start

    # Detect Windows crash codes
    code = result.return_code
    if code < 0:
        unsigned = code + (1 << 32)  # Python stores as signed
    else:
        unsigned = code

    if unsigned in _CRASH_CODES:
        result.crash_reason = _CRASH_CODES[unsigned]
    elif code < 0:
        result.crash_reason = f"NEGATIVE_EXIT({code})"

    # Log outcome
    if result.crashed:
        print(f"  [Runner] CRASHED: {result.crash_reason} ({result.duration_seconds:.1f}s)")
    elif result.timed_out:
        print(f"  [Runner] TIMEOUT after {timeout}s")
    else:
        print(f"  [Runner] Exited: code={result.return_code} ({result.duration_seconds:.1f}s)")

    return result
