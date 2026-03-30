"""Unit tests for memory leak parsing."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.memleak_test import _parse_crt_leaks, _parse_memleaks_file


def test_no_leaks_in_output():
    count, _ = _parse_crt_leaks("Application exited normally.\n")
    assert count == 0


def test_crt_leak_detected():
    output = """Detected memory leaks!
Dumping objects ->
{123} normal block at 0x00AB1234, 64 bytes long.
{456} normal block at 0x00CD5678, 128 bytes long.
Object dump complete.
"""
    count, details = _parse_crt_leaks(output)
    assert count == 2
    assert len(details) == 2
    assert "123" in details[0]


def test_crt_header_only():
    output = "Detected memory leaks!\nNo details available.\n"
    count, details = _parse_crt_leaks(output)
    assert count == 1  # header found but no blocks parsed


def test_memleaks_file(tmp_path):
    f = tmp_path / "test.memleaks"
    f.write_text("3 memory leaks found:\nleak 1\nleak 2\nleak 3\n")
    count, details = _parse_memleaks_file(f)
    assert count == 3


def test_memleaks_file_no_leaks(tmp_path):
    f = tmp_path / "test.memleaks"
    f.write_text("0 memory leaks found:\n")
    count, _ = _parse_memleaks_file(f)
    assert count == 0


def test_memleaks_file_missing():
    count, _ = _parse_memleaks_file(Path("/nonexistent/file.memleaks"))
    assert count == 0
