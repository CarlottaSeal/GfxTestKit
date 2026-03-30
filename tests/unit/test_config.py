"""Unit tests for config loading and path resolution."""
import json
import sys
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config, ProjectConfig


def _write_config(tmp_path: Path, data: dict) -> Path:
    cfg_path = tmp_path / "test_project.json"
    with open(cfg_path, "w") as f:
        json.dump(data, f)
    return cfg_path


def test_load_minimal_config(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "app.exe",
    })
    cfg = load_config(cfg_path)
    assert cfg.name == "TestApp"
    assert cfg.exe_path.endswith("app.exe")
    assert cfg.benchmark_enabled is False
    assert cfg.shader_compile_enabled is False


def test_benchmark_thresholds_defaults(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "app.exe",
        "benchmark": {"enabled": True, "args": ["--benchmark", "100"]},
    })
    cfg = load_config(cfg_path)
    assert cfg.benchmark_enabled is True
    assert cfg.benchmark_thresholds["avg_fps_pct"] == 10.0
    assert cfg.benchmark_thresholds["p1_fps_pct"] == 15.0


def test_relative_paths_resolved(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "../bin/app.exe",
        "benchmark": {
            "enabled": True,
            "result_file": "output/results.json",
            "baseline_file": "../baselines/base.json",
        },
    })
    cfg = load_config(cfg_path)
    # Paths should be resolved to absolute
    assert Path(cfg.exe_path).is_absolute()
    assert Path(cfg.benchmark_result_file).is_absolute()
    assert "output" in cfg.benchmark_result_file


def test_build_config(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "app.exe",
        "build": {
            "enabled": True,
            "solution": "project.sln",
            "configuration": "Debug",
            "platform": "Win32",
        },
    })
    cfg = load_config(cfg_path)
    assert cfg.build_enabled is True
    assert cfg.build_configuration == "Debug"
    assert cfg.build_platform == "Win32"


def test_memleak_config(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "app.exe",
        "memleak": {
            "enabled": True,
            "args": ["--benchmark", "60"],
            "file": "leaks.memleaks",
        },
    })
    cfg = load_config(cfg_path)
    assert cfg.memleak_enabled is True
    assert cfg.memleak_args == ["--benchmark", "60"]


def test_warmup_frames_custom(tmp_path):
    cfg_path = _write_config(tmp_path, {
        "name": "TestApp",
        "exe_path": "app.exe",
        "benchmark": {
            "enabled": True,
            "warmup_frames": 120,
        },
    })
    cfg = load_config(cfg_path)
    assert cfg.benchmark_warmup_frames == 120
