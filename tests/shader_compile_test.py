"""
shader_compile_test.py - HLSL shader compilation validation.

Scans directories for .hlsl files and compiles each with dxc.exe (or fxc.exe).
Detects compilation errors and tracks warning count regression.

Inspired by The-Forge's PyBuildShaders.py and FSL analysis pipeline.
"""

import subprocess
import time
from pathlib import Path

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.config import ProjectConfig
from core.report import TestResult


def _find_shaders(dirs: list[str], extensions: tuple = (".hlsl",)) -> list[Path]:
    """Recursively find all shader files in the given directories."""
    shaders = []
    for d in dirs:
        path = Path(d)
        if not path.exists():
            print(f"  [Shader] WARNING: directory not found: {path}")
            continue
        for ext in extensions:
            shaders.extend(sorted(path.rglob(f"*{ext}")))
    return shaders


def _detect_entries(shader_path: Path) -> list[tuple[str, str]]:
    """
    Detect all entry points and their profiles from shader source.

    Scans for:
      - [numthreads(...)] → next function is CS
      - : SV_POSITION in return → VS
      - : SV_TARGET in return → PS

    Returns list of (entry_name, profile) pairs. A single file can have
    multiple entry points (e.g. CompositeVS + CompositePS).
    """
    import re

    try:
        with open(shader_path, "r", errors="replace") as f:
            source = f.read()
    except Exception:
        return [("main", "ps_6_0")]

    entries = []
    lines = source.split("\n")
    is_next_cs = False

    for line in lines:
        stripped = line.strip()

        # [numthreads(X, Y, Z)] marks the next function as compute
        if re.match(r"\[numthreads\s*\(", stripped):
            is_next_cs = True
            continue

        # Function signature: "ReturnType FuncName(...) : SEMANTIC" or just "void FuncName(...)"
        func_match = re.match(
            r"(?:float4|void|uint|int|float|half4|VSOutput|PSOutput)\s+(\w+)\s*\(",
            stripped,
        )
        if not func_match:
            continue

        func_name = func_match.group(1)

        if is_next_cs:
            entries.append((func_name, "cs_6_0"))
            is_next_cs = False
        elif ": SV_POSITION" in line or ": SV_Position" in line:
            entries.append((func_name, "vs_6_0"))
        elif ": SV_TARGET" in line or ": SV_Target" in line:
            entries.append((func_name, "ps_6_0"))

    if not entries:
        # Fallback: check if file has [numthreads] anywhere
        if "[numthreads" in source:
            return [("main", "cs_6_0")]
        return [("main", "ps_6_0")]

    return entries


def _compile_shader(
    compiler: str,
    shader_path: Path,
    entry: str,
    profile: str,
    extra_args: list[str],
) -> dict:
    """
    Compile a single shader and return result dict.
    """
    cmd = [compiler, str(shader_path), "-E", entry, "-T", profile, "-nologo"]
    # Add include path: shader's own directory (for local #includes)
    cmd.extend(["-I", str(shader_path.parent)])
    cmd.extend(extra_args)
    # Don't write output file, just validate
    cmd.append("-Fo")
    cmd.append("NUL")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        output = proc.stdout + proc.stderr

        errors = output.count("error:")
        warnings = output.count("warning:")

        return {
            "passed": proc.returncode == 0 and errors == 0,
            "return_code": proc.returncode,
            "errors": errors,
            "warnings": warnings,
            "output": output.strip() if not (proc.returncode == 0 and errors == 0) else "",
        }
    except FileNotFoundError:
        return {
            "passed": False, "return_code": -1, "errors": 1, "warnings": 0,
            "output": f"Compiler not found: {compiler}",
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False, "return_code": -1, "errors": 1, "warnings": 0,
            "output": "Compilation timed out",
        }


def run(cfg: ProjectConfig, update_baseline: bool = False) -> TestResult:
    """
    Compile all HLSL shaders and report errors/warnings.
    """
    start = time.time()
    shaders = _find_shaders(cfg.shader_dirs)

    if not shaders:
        return TestResult(
            name="shader_compile", status="SKIP", return_code=RET_SUCCESS,
            message="No shaders found to compile",
            duration_seconds=time.time() - start,
        )

    compiler = cfg.shader_compiler
    extra_args = cfg.shader_args
    ret_code = RET_SUCCESS
    total_errors = 0
    total_warnings = 0
    failures = []
    details = {}

    # Collect all include dirs from shader_dirs (for cross-directory #includes)
    include_args = []
    for d in cfg.shader_dirs:
        p = Path(d)
        if p.exists():
            include_args.extend(["-I", str(p)])
            # Also add subdirectories as include paths
            for sub in p.iterdir():
                if sub.is_dir():
                    include_args.extend(["-I", str(sub)])

    all_extra = extra_args + include_args
    total_entries = 0

    print(f"  [Shader] Compiling {len(shaders)} shaders with {compiler}")

    for shader in shaders:
        entries = _detect_entries(shader)
        rel_name = shader.name

        for entry, profile in entries:
            total_entries += 1
            result = _compile_shader(compiler, shader, entry, profile, all_extra)

            key = f"{rel_name}:{entry}"
            total_errors += result["errors"]
            total_warnings += result["warnings"]
            details[key] = result

            if not result["passed"]:
                ret_code = max(ret_code, RET_CRITICAL)
                failures.append(key)
                print(f"  [Shader] {rel_name} ({entry} {profile}): FAIL ({result['errors']} errors)")
                if result["output"]:
                    for line in result["output"].split("\n")[:3]:
                        print(f"           {line}")
            else:
                warn_str = f" ({result['warnings']} warnings)" if result["warnings"] > 0 else ""
                print(f"  [Shader] {rel_name} ({entry} {profile}): OK{warn_str}")

    if ret_code == RET_SUCCESS:
        msg = f"All {total_entries} entries in {len(shaders)} shaders compiled ({total_warnings} warnings)"
        status = "PASS"
    else:
        msg = f"{len(failures)}/{total_entries} entries failed to compile"
        status = "FAIL"

    return TestResult(
        name="shader_compile", status=status, return_code=ret_code,
        message=msg,
        details={"total_errors": total_errors, "total_warnings": total_warnings, "files": details},
        duration_seconds=time.time() - start,
    )
