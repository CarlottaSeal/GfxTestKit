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
  stats.py                   statistical analysis (outlier, trend, changepoint)
tests/
  build_test.py              MSBuild automation (locates via vswhere)
  benchmark_test.py          FPS baseline comparison (median of 3 runs)
  screenshot_test.py         PSNR/SSIM image regression
  shader_compile_test.py     HLSL compilation via dxc with auto entry detection
  memleak_test.py            Memory leak detection (.memleaks + CRT output)
  sanitizer_test.py          ASAN/UBSAN error parsing
  unit/                      64 pytest unit tests for the tool itself
projects/
  luminagi.json              example project config
.github/workflows/ci.yml     GitHub Actions: lint + pytest on every push
```

### gfx_test.py — Entry point

Parses CLI arguments (`--project`, `--test`, `--update-baseline`, `--report`), loads the config, then runs each enabled test module in a fixed order: build → benchmark → screenshot → shader\_compile → memleak → sanitizer. If build fails, the remaining tests are skipped immediately — no point benchmarking broken code. Each test's result is handed to `Report`, which tracks the worst return code across all tests and uses it as the process exit code.

### core/config.py — Project configuration

Defines `ProjectConfig`, a flat dataclass that holds all settings for one test target. `load_config(path)` reads the JSON file, maps each section (`benchmark`, `screenshot`, `shader_compile`, `build`, `sanitizer`, `memleak`) into the corresponding fields, then calls `resolve_paths` to convert any relative paths to absolute paths based on the config file's location. This means config files are portable — you can move the `projects/` folder without breaking paths.

### core/runner.py — Process lifecycle

`launch(exe_path, args, working_dir, timeout, env)` is the single function that every test module calls to run the target application. It wraps `subprocess.Popen`, captures stdout and stderr, enforces a timeout, and on exit translates Windows NT exception codes (like `0xC0000005` ACCESS\_VIOLATION or `0xC00000FD` STACK\_OVERFLOW) into readable crash reasons. Without this translation, a graphics app crash returns a negative integer that is meaningless without knowing Windows NT status codes.

### core/report.py — Result collection

`Report` accumulates `TestResult` objects from each test module and produces two outputs: a formatted console table via `print_summary()` and an optional JSON file via `save_json()`. The `worst_code` property returns the highest return code seen across all results — `0x00` if everything passed, `0x02` for warnings, `0xFF` for any failure. This single value becomes the process exit code, which is what CI checks.

### core/stats.py — Performance time series analysis

Used by the benchmark test after 5 or more historical runs accumulate. Takes a list of FPS values over time and runs four analyses using Python stdlib only (no numpy or scipy):

| Function | What it does |
|----------|-------------|
| `compute_summary` | Mean, median, stdev, CV, p5/p95, min/max |
| `detect_outliers_zscore` | Flags points beyond N standard deviations |
| `detect_outliers_iqr` | IQR fence method, more robust to skewed distributions |
| `detect_trend` | OLS linear regression slope + recent-window vs overall-mean comparison |
| `detect_changepoints` | Sliding-window Welch's t-test to find sudden performance shifts |
| `analyze_series` | Runs all of the above and returns a `SeriesAnalysis` bundle |

The changepoint detector is the most useful for CI: it catches a sudden 10% regression introduced by a specific commit, which a simple baseline comparison might miss if the baseline was set long ago.

### tests/build\_test.py — MSBuild

Locates `MSBuild.exe` via `vswhere.exe` (the standard VS installation query tool), then invokes it on the configured `.sln` file. Parses stdout to count errors and warnings. Any error is a critical failure; warnings are reported but do not block subsequent tests when run in isolation.

### tests/benchmark\_test.py — FPS regression

Launches the application three times with `--benchmark <frames>` and reads the JSON result file it produces. Uses the median of the three runs as the comparison value — this filters noise from background system load. Compares against a stored baseline using configurable per-metric thresholds (`avg_fps_pct`, `p1_fps_pct`, `p5_fps_pct`, `min_fps_pct`). Appends each run to a history file; once 5+ entries exist, runs `stats.analyze_series` for trend and changepoint detection.

### tests/screenshot\_test.py — Image regression

Launches the application, then compares each output screenshot against a stored reference using PSNR as the primary metric (default threshold: 70 dB). A 16-pixel safety valve forces a pass if fewer than 16 pixels differ — this handles floating-point rendering jitter that varies across driver versions without failing CI. Diff images are saved alongside the outputs for visual inspection. `scikit-image` is lazy-imported so non-screenshot runs pay no import cost.

### tests/shader\_compile\_test.py — HLSL batch compilation

Scans configured directories for `.hlsl` files and compiles each with `dxc.exe`. Entry points are auto-detected by scanning the source for `[numthreads]` (compute), `SV_Position` (vertex), `SV_Target` / `SV_Depth` (pixel/depth), and struct return types containing these semantics. Files with multiple entry points (e.g. a VS + PS in one file) are compiled separately for each. If detection fails, common fallback names (`VertexMain`, `PixelMain`, `CSMain`, etc.) are tried before reporting a warning.

### tests/memleak\_test.py — Memory leak detection

Launches the application and checks for leaks through two channels: parsing `.memleaks` files (The-Forge convention, contains leak count and details) and scanning stdout/stderr for MSVC CRT debug output (`_CrtDumpMemoryLeaks`). Any leak found is a critical failure.

### tests/sanitizer\_test.py — ASAN / UBSAN

Runs a separately compiled instrumented build and parses its output for sanitizer errors. Automatically sets `ASAN_OPTIONS` and `UBSAN_OPTIONS` environment variables to enable verbose stack traces. Recognizes AddressSanitizer patterns (heap-buffer-overflow, use-after-free, double-free) and UndefinedBehaviorSanitizer patterns (integer overflow, null pointer dereference, misaligned access). Requires a build compiled with `/fsanitize=address` (MSVC) or `-fsanitize=address,undefined` (clang-cl).

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

Each run is automatically appended to a history file. Once 5+ runs exist, statistical trend analysis runs after every benchmark:
- **Outlier detection**: Z-score and IQR methods flag abnormal runs
- **Trend analysis**: OLS linear regression detects gradual degradation that single-baseline comparisons miss
- **Changepoint detection**: sliding-window Welch's t-test identifies sudden performance shifts
- **Smoothing**: simple and exponential moving averages for noisy data

All statistics use Python stdlib only (no numpy/scipy dependency).

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
- 64 unit tests via pytest (config, report, leak parsing, shader detection, sanitizer parsing, statistical analysis)

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
