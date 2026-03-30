"""Unit tests for shader entry point detection."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.shader_compile_test import _detect_entries


def _write_shader(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_compute_shader(tmp_path):
    shader = _write_shader(tmp_path, "test.hlsl", """
[numthreads(8, 8, 1)]
void CSMain(uint3 id : SV_DispatchThreadID) {}
""")
    entries = _detect_entries(shader)
    assert ("CSMain", "cs_6_0") in entries


def test_vs_ps_shader(tmp_path):
    shader = _write_shader(tmp_path, "test.hlsl", """
struct VSOutput { float4 pos : SV_Position; };
struct PSOutput { float4 color : SV_Target0; };

VSOutput VertexMain(uint id : SV_VertexID) { VSOutput o; return o; }
PSOutput PixelMain(VSOutput input) { PSOutput o; return o; }
""")
    entries = _detect_entries(shader)
    assert ("VertexMain", "vs_6_0") in entries
    assert ("PixelMain", "ps_6_0") in entries


def test_sv_depth_is_ps(tmp_path):
    shader = _write_shader(tmp_path, "test.hlsl", """
struct VSOutput { float4 pos : SV_Position; };
VSOutput VS(uint id : SV_VertexID) { VSOutput o; return o; }
float PS(VSOutput input) : SV_Depth { return 1.0; }
""")
    entries = _detect_entries(shader)
    assert ("VS", "vs_6_0") in entries
    assert ("PS", "ps_6_0") in entries


def test_empty_shader_fallback(tmp_path):
    shader = _write_shader(tmp_path, "empty.hlsl", "// empty\n")
    entries = _detect_entries(shader)
    assert len(entries) == 1
    assert entries[0] == ("main", "ps_6_0")


def test_numthreads_fallback(tmp_path):
    shader = _write_shader(tmp_path, "test.hlsl", """
// some compute shader
cbuffer CB : register(b0) { uint N; }
[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {}
""")
    entries = _detect_entries(shader)
    assert any(profile == "cs_6_0" for _, profile in entries)
