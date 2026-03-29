# GfxTestKit

Test automation for graphics applications： benchmark regression, screenshot diff, shader compilation checks.

Built for my DX12 rendering engine: my Igloo Engine needed a way to catch performance regressions and shader breakage automatically after code changes. Designed to work with any graphics application through a JSON project config.

## Quick Start

```bash
pip install scikit-image numpy

# Run all tests against a project
python gfx_test.py --project projects/luminagi.json

# Establish performance baseline first
python gfx_test.py --project projects/luminagi.json --update-baseline

# Run a single test type
python gfx_test.py --project projects/luminagi.json --test benchmark
python gfx_test.py --project projects/luminagi.json --test shader_compile
python gfx_test.py --project projects/luminagi.json --test screenshot
```

## Architecture

### How it's organized

`gfx_test.py` is the entry point. It reads a project config, runs the enabled tests, and aggregates results.

The `core/` layer handles the plumbing — launching processes (`runner.py`), loading JSON configs (`config.py`), and collecting results into a report (`report.py`).

The `tests/` layer has one module per test type. Each takes a config and returns a pass/warn/fail result. The orchestrator doesn't know or care what happens inside.

```
gfx_test.py                  entry point, arg parsing, test sequencing
core/
  runner.py                  subprocess launch, timeout, crash code detection
  config.py                  JSON project config loading
  report.py                  result aggregation, console + JSON output
tests/
  benchmark_test.py          FPS baseline comparison
  screenshot_test.py         PSNR/SSIM image regression
  shader_compile_test.py     HLSL compilation via dxc
projects/
  luminagi.json              example project config
```

### Why it works this way

All test targets are defined in JSON — swap out one config file and the same tool tests a different app. No code changes needed.

Each test module exposes `run(cfg, update_baseline)` and returns a `TestResult`. The orchestrator doesn't care what happens inside.

Return codes follow `0x00` / `0x02` / `0xFF` (pass / warning / critical). The worst code wins. This makes it easy to plug into CI — just check the exit code.

`runner.py` catches Windows crash codes like `0xC0000005` (access violation) so you get a readable crash reason instead of a mysterious negative exit code.

Screenshot comparison uses a two-gate approach: first check PSNR against a threshold (default 70 dB), but if fewer than 16 pixels actually differ, force a pass anyway — floating-point jitter across driver versions shouldn't fail your build. scikit-image is lazy-imported so it doesn't slow down runs that don't need it.

Shader entry points are auto-detected by scanning the source for `[numthreads]`, `: SV_POSITION`, `: SV_TARGET`. Files with both a VS and PS get compiled twice, once for each.

Target apps integrate through 4 global functions (`Startup` / `EndFrame` / `ShouldQuit` / `Shutdown`) — same pattern as a typical engine debug render system. No base class, no framework dependency.

### Benchmark flow

The orchestrator launches the app with `--benchmark 600`, the engine runs that many frames, writes a JSON with FPS stats (avg/min/p1/p5/median), and exits. The test module reads the JSON, compares each metric against the stored baseline, and flags regressions that exceed the configured thresholds.

## Test Types

### Benchmark
Launches the application with `--benchmark <frames>`, collects the FPS metrics JSON, and compares against a stored baseline. Configurable per-metric percentage thresholds detect regressions.

Requires the target application to support:
- `--benchmark N` (run N frames and exit)
- `--output <path>` (write results JSON)

### Screenshot Regression
Compares rendered screenshots against reference images using scikit-image:
- **PSNR** as the primary metric (default threshold: 70 dB)
- **16-pixel safety valve**: fewer than 16 differing pixels forces a pass (handles floating-point jitter)
- Diff images saved for visual inspection
- Reference-driven traversal ensures missing screenshots are caught

### Shader Compilation
Scans directories for `.hlsl` files and compiles each with `dxc.exe`:
- Auto-detects entry points by scanning source for `[numthreads]`, `SV_POSITION`, `SV_TARGET`
- Handles multi-entry files (e.g., VS + PS in the same file)
- Include paths automatically derived from shader directories

## Project Configuration

Create a JSON file in `projects/` to define a test target:

```json
{
    "name": "MyApp",
    "exe_path": "../path/to/MyApp.exe",
    "working_dir": "../path/to/Run",
    "timeout": 180,
    "benchmark": {
        "enabled": true,
        "args": ["--benchmark", "600", "--output", "benchmark_results.json"],
        "result_file": "../path/to/Run/benchmark_results.json",
        "baseline_file": "../baselines/myapp/benchmark.json",
        "thresholds": { "avg_fps_pct": 10.0, "p1_fps_pct": 15.0 }
    },
    "shader_compile": {
        "enabled": true,
        "dirs": ["../path/to/Shaders"],
        "compiler": "dxc.exe"
    }
}
```

## Engine Integration

For the benchmark test to work, the target application needs a small automation hook. An example implementation for a C++ engine(my IglooEngine) using the global-function pattern:

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

## Return Codes

Exit codes follow a severity convention: `0x00` means all clear, `0x02` means warnings (minor screenshot diff, small perf delta), `0xFF` means something broke (crash, major regression, compile error). The worst result across all tests becomes the process exit code.

## Example Output

```
============================================================
  TEST REPORT: LuminaGI
============================================================
  [+] benchmark                      PASS       11.6s
      No regression (avg_fps=145.8)
  [!] shader_compile                 FAIL       1.6s
      5/33 entries failed to compile
============================================================
  Total: 2 tests in 13.3s
  Result: FAIL (exit code 0xFF)
============================================================
```
