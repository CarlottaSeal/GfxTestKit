# GfxTestKit

[![CI](https://github.com/CarlottaSeal/GfxTestKit/actions/workflows/ci.yml/badge.svg)](https://github.com/CarlottaSeal/GfxTestKit/actions/workflows/ci.yml)

Test automation for graphics applications: build, benchmark regression, screenshot diff, shader compilation, memory leak detection.

Built for my DX12 rendering engine: my Igloo Engine needed a way to catch performance regressions and shader breakage automatically after code changes. Designed to work with any graphics application through a JSON project config.

## Quick Start

```bash
pip install -r requirements.txt

# Run all tests against a project
python gfx_test.py --project projects/luminagi.json

# Establish performance baseline first
python gfx_test.py --project projects/luminagi.json --update-baseline

# Run a single test type
python gfx_test.py --project projects/luminagi.json --test build
python gfx_test.py --project projects/luminagi.json --test benchmark
python gfx_test.py --project projects/luminagi.json --test shader_compile
python gfx_test.py --project projects/luminagi.json --test memleak
python gfx_test.py --project projects/luminagi.json --test sanitizer
```

## Architecture

### How it's organized

`gfx_test.py` is the entry point. It reads a project config, runs the enabled tests in order, and aggregates results. If the build step fails, it skips everything else.

The `core/` layer handles the plumbing — launching processes (`runner.py`), loading JSON configs (`config.py`), and collecting results into a report (`report.py`).

The `tests/` layer has one module per test type. Each takes a config and returns a pass/warn/fail result. The orchestrator doesn't know or care what happens inside.

```
gfx_test.py                  entry point, arg parsing, test sequencing
core/
  runner.py                  subprocess launch, timeout, crash code detection
  config.py                  JSON project config loading
  report.py                  result aggregation, console + JSON output
tests/
  build_test.py              MSBuild automation (locates via vswhere)
  benchmark_test.py          FPS baseline comparison (median of 3 runs)
  screenshot_test.py         PSNR/SSIM image regression
  shader_compile_test.py     HLSL compilation via dxc with auto entry detection
  memleak_test.py            Memory leak detection (.memleaks + CRT output)
  sanitizer_test.py          ASAN/UBSAN error parsing
  unit/                      29 pytest unit tests for the tool itself
projects/
  luminagi.json              example project config
.github/workflows/ci.yml     GitHub Actions: lint + pytest on every push
```

### Why it works this way

All test targets are defined in JSON — swap out one config file and the same tool tests a different app. No code changes needed.

Each test module exposes `run(cfg, update_baseline)` and returns a `TestResult`. The orchestrator doesn't care what happens inside.

Return codes follow `0x00` / `0x02` / `0xFF` (pass / warning / critical). The worst code wins. This makes it easy to plug into CI — just check the exit code.

`runner.py` catches Windows crash codes like `0xC0000005` (access violation) so you get a readable crash reason instead of a mysterious negative exit code.

Screenshot comparison uses a two-gate approach: first check PSNR against a threshold (default 70 dB), but if fewer than 16 pixels actually differ, force a pass anyway — floating-point jitter across driver versions shouldn't fail your build. scikit-image is lazy-imported so it doesn't slow down runs that don't need it.

Shader entry points are auto-detected by scanning the source for `[numthreads]`, `SV_Position`, `SV_Target`, `SV_Depth`, and struct return types containing these semantics. Files with multiple entries (VS + PS) get compiled separately. If detection fails, common fallback names (VertexMain, PixelMain, etc.) are tried before reporting a warning.

Benchmark results use the median of 3 runs for both baseline and comparison, which filters out noise from background system load.

Build failure automatically skips all downstream tests — no point benchmarking broken code.

Memory leak detection parses both `.memleaks` files (The-Forge convention) and MSVC CRT debug output (`_CrtDumpMemoryLeaks`). Any leak is a critical failure.

Sanitizer support parses stdout/stderr for AddressSanitizer (heap-buffer-overflow, use-after-free, double-free) and UndefinedBehaviorSanitizer (integer overflow, null pointer, misaligned access) error patterns. Requires a separate instrumented build; the tool automatically sets `ASAN_OPTIONS` and `UBSAN_OPTIONS` env vars.

Target apps integrate through 4 global functions (`Startup` / `EndFrame` / `ShouldQuit` / `Shutdown`) — same pattern as a typical engine debug render system. No base class, no framework dependency.

## Test Types

### Build
Compiles the project via MSBuild (auto-located through vswhere). Parses error/warning counts from output. Build failure skips all remaining tests.

### Benchmark
Launches the application with `--benchmark <frames>`, collects FPS metrics JSON, and compares against a stored baseline. Both baseline and comparison use the median of 3 runs. Configurable per-metric percentage thresholds (avg, p1, p5, min) detect regressions.

### Screenshot Regression
Compares rendered screenshots against reference images using scikit-image:
- PSNR as the primary metric (default threshold: 70 dB)
- 16-pixel safety valve: fewer than 16 differing pixels forces a pass (handles floating-point jitter)
- Diff images saved for visual inspection
- Reference-driven traversal ensures missing screenshots are caught

### Shader Compilation
Scans directories for `.hlsl` files and compiles each with `dxc.exe`:
- Auto-detects entry points by scanning source for semantics and struct return types
- Handles multi-entry files (e.g., VS + PS in the same file)
- Fallback entry names tried before giving up (warning vs failure)
- Include paths automatically derived from shader directories

### Memory Leak Detection
Detects memory leaks through two channels:
- Parses `.memleaks` files (count + details)
- Scans stdout/stderr for MSVC CRT leak reports
- Any leak = critical failure (0xFF)

### Sanitizer (ASAN/UBSAN)
Runs an instrumented build and parses output for sanitizer errors:
- AddressSanitizer: buffer overflow, use-after-free, double-free, leak detection
- UndefinedBehaviorSanitizer: integer overflow, null pointer, misaligned access
- Automatically sets `ASAN_OPTIONS` and `UBSAN_OPTIONS` for detailed stack traces
- Requires a separate build with `/fsanitize=address` (MSVC) or `-fsanitize=address,undefined` (clang-cl)

## Project Configuration

Create a JSON file in `projects/` to define a test target:

```json
{
    "name": "MyApp",
    "exe_path": "../path/to/MyApp.exe",
    "working_dir": "../path/to/Run",
    "timeout": 180,
    "build": {
        "enabled": true,
        "solution": "../path/to/Project.sln",
        "configuration": "Release",
        "platform": "x64"
    },
    "benchmark": {
        "enabled": true,
        "args": ["--benchmark", "600", "--output", "benchmark_results.json"],
        "result_file": "../path/to/Run/benchmark_results.json",
        "baseline_file": "../baselines/myapp/benchmark.json",
        "warmup_frames": 60,
        "thresholds": { "avg_fps_pct": 10.0, "p1_fps_pct": 15.0 }
    },
    "shader_compile": {
        "enabled": true,
        "dirs": ["../path/to/Shaders"],
        "compiler": "dxc.exe"
    },
    "memleak": {
        "enabled": false,
        "args": ["--benchmark", "120"],
        "file": ""
    },
    "sanitizer": {
        "enabled": false,
        "exe_path": "../path/to/MyApp_ASAN.exe",
        "type": "asan",
        "args": ["--benchmark", "120"]
    }
}
```

## Engine Integration

For the benchmark test to work, the target application needs a small automation hook. An example implementation for a C++ engine (my Igloo Engine) using the global-function pattern:

```cpp
// AutomatedTesting.hpp - Engine level, any project can use
void AutomatedTestingStartup(const char* commandLine);  // parse --benchmark N
void AutomatedTestingEndFrame();                          // record FPS each frame
bool AutomatedTestingShouldQuit();                        // true when done
void AutomatedTestingShutdown();                          // write JSON results

// Game's App.cpp - 4 lines of integration
AutomatedTestingStartup(commandLineString);               // at startup
AutomatedTestingEndFrame();                                // each frame
if (AutomatedTestingShouldQuit()) HandleQuitRequested();   // each frame
AutomatedTestingShutdown();                                // at shutdown
```

## CI

GitHub Actions runs on every push:
- Python syntax validation across all `.py` files
- 29 unit tests via pytest (config, report, leak parsing, shader detection, sanitizer parsing)

Full GPU integration tests are documented for self-hosted runners with GPU hardware.

## Return Codes

Exit codes follow a severity convention: `0x00` means all clear, `0x02` means warnings (minor screenshot diff, small perf delta), `0xFF` means something broke (crash, major regression, compile error). The worst result across all tests becomes the process exit code.

## Example Output

```
============================================================
  TEST REPORT: LuminaGI
============================================================
  [+] build                          PASS       20.5s
      Build succeeded (6 warnings)
  [+] benchmark                      PASS       34.5s
      No regression (avg_fps=153.4)
  [!] shader_compile                 FAIL       1.5s
      2/38 entries failed to compile
============================================================
  Total: 3 tests in 58.6s
  Result: FAIL (exit code 0xFF)
============================================================
```
