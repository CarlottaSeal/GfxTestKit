"""
config.py - Load and validate JSON project configuration.

A project config defines the test target and what tests to run.
See projects/luminagi.json for an example.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectConfig:
    """Parsed project configuration."""
    name: str = ""
    exe_path: str = ""
    working_dir: str = ""
    timeout: int = 120

    # Benchmark test settings
    benchmark_enabled: bool = False
    benchmark_args: list[str] = field(default_factory=list)
    benchmark_result_file: str = ""
    benchmark_baseline_file: str = ""
    benchmark_warmup_frames: int = 60
    benchmark_thresholds: dict[str, float] = field(default_factory=dict)

    # Screenshot test settings
    screenshot_enabled: bool = False
    screenshot_args: list[str] = field(default_factory=list)
    screenshot_output_dir: str = ""
    screenshot_reference_dir: str = ""
    screenshot_psnr_threshold: float = 70.0

    # Shader compilation test settings
    shader_compile_enabled: bool = False
    shader_dirs: list[str] = field(default_factory=list)
    shader_compiler: str = "dxc.exe"
    shader_args: list[str] = field(default_factory=list)

    # Build settings
    build_enabled: bool = False
    build_solution: str = ""
    build_configuration: str = "Release"
    build_platform: str = "x64"
    build_msbuild_path: str = ""
    build_timeout: int = 300

    # Memory leak detection settings
    memleak_enabled: bool = False
    memleak_args: list[str] = field(default_factory=list)
    memleak_file: str = ""  # path to .memleaks file (optional)

    # Extra environment variables to inject (like The-Forge's AUTOMATED_TESTING)
    env_vars: dict[str, str] = field(default_factory=dict)

    def resolve_paths(self, base_dir: Path):
        """Resolve relative paths against the config file's directory."""
        def resolve(p: str) -> str:
            if not p:
                return ""
            path = Path(p)
            if not path.is_absolute():
                path = base_dir / path
            return str(path.resolve())

        self.exe_path = resolve(self.exe_path)
        self.working_dir = resolve(self.working_dir) if self.working_dir else ""
        self.benchmark_result_file = resolve(self.benchmark_result_file)
        self.benchmark_baseline_file = resolve(self.benchmark_baseline_file)
        self.screenshot_output_dir = resolve(self.screenshot_output_dir)
        self.screenshot_reference_dir = resolve(self.screenshot_reference_dir)
        self.shader_dirs = [resolve(d) for d in self.shader_dirs]
        self.build_solution = resolve(self.build_solution)
        self.memleak_file = resolve(self.memleak_file) if self.memleak_file else ""


def load_config(config_path: str | Path) -> ProjectConfig:
    """Load a project config JSON and return a ProjectConfig."""
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r") as f:
        raw: dict[str, Any] = json.load(f)

    cfg = ProjectConfig()
    cfg.name = raw.get("name", config_path.stem)
    cfg.exe_path = raw.get("exe_path", "")
    cfg.working_dir = raw.get("working_dir", "")
    cfg.timeout = raw.get("timeout", 120)
    cfg.env_vars = raw.get("env_vars", {})

    bench = raw.get("benchmark", {})
    if bench:
        cfg.benchmark_enabled = bench.get("enabled", False)
        cfg.benchmark_args = bench.get("args", [])
        cfg.benchmark_result_file = bench.get("result_file", "")
        cfg.benchmark_baseline_file = bench.get("baseline_file", "")
        cfg.benchmark_warmup_frames = bench.get("warmup_frames", 60)
        cfg.benchmark_thresholds = bench.get("thresholds", {
            "avg_fps_pct": 10.0,
            "p1_fps_pct": 15.0,
        })

    ss = raw.get("screenshot", {})
    if ss:
        cfg.screenshot_enabled = ss.get("enabled", False)
        cfg.screenshot_args = ss.get("args", [])
        cfg.screenshot_output_dir = ss.get("output_dir", "")
        cfg.screenshot_reference_dir = ss.get("reference_dir", "")
        cfg.screenshot_psnr_threshold = ss.get("psnr_threshold", 70.0)

    sc = raw.get("shader_compile", {})
    if sc:
        cfg.shader_compile_enabled = sc.get("enabled", False)
        cfg.shader_dirs = sc.get("dirs", [])
        cfg.shader_compiler = sc.get("compiler", "dxc.exe")
        cfg.shader_args = sc.get("args", [])

    build = raw.get("build", {})
    if build:
        cfg.build_enabled = build.get("enabled", False)
        cfg.build_solution = build.get("solution", "")
        cfg.build_configuration = build.get("configuration", "Release")
        cfg.build_platform = build.get("platform", "x64")
        cfg.build_msbuild_path = build.get("msbuild_path", "")
        cfg.build_timeout = build.get("timeout", 300)

    ml = raw.get("memleak", {})
    if ml:
        cfg.memleak_enabled = ml.get("enabled", False)
        cfg.memleak_args = ml.get("args", [])
        cfg.memleak_file = ml.get("file", "")

    cfg.resolve_paths(config_path.parent)
    return cfg
