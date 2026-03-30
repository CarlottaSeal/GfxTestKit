"""Unit tests for sanitizer output parsing."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sanitizer_test import _parse_sanitizer_output, _extract_summary


def test_clean_output():
    count, _ = _parse_sanitizer_output("Application ran normally.\nExit code 0\n")
    assert count == 0


def test_asan_heap_buffer_overflow():
    output = """
==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000014
READ of size 4 at 0x602000000014 thread T0
    #0 0x4c3a45 in main test.cpp:10
SUMMARY: AddressSanitizer: heap-buffer-overflow test.cpp:10 in main
"""
    count, errors = _parse_sanitizer_output(output)
    assert count == 2  # ERROR line + heap-buffer-overflow line
    assert any("heap-buffer-overflow" in e for e in errors)


def test_asan_use_after_free():
    output = "ERROR: AddressSanitizer: use-after-free on address 0x123\n"
    count, _ = _parse_sanitizer_output(output)
    assert count >= 1


def test_ubsan_runtime_error():
    output = """
test.cpp:15:10: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
SUMMARY: UndefinedBehaviorSanitizer: signed-integer-overflow test.cpp:15:10
"""
    count, errors = _parse_sanitizer_output(output)
    assert count >= 1
    assert any("runtime error" in e for e in errors)


def test_leak_sanitizer():
    output = """
==12345==ERROR: LeakSanitizer: detected memory leaks
Direct leak of 64 byte(s) in 1 object(s) allocated from:
    #0 0x7f1234 in malloc
SUMMARY: AddressSanitizer: 64 byte(s) leaked in 1 allocation(s).
"""
    count, _ = _parse_sanitizer_output(output)
    assert count >= 1


def test_extract_summary():
    output = "lots of stuff\nSUMMARY: AddressSanitizer: heap-buffer-overflow test.cpp:10\nmore stuff\n"
    summary = _extract_summary(output)
    assert "SUMMARY" in summary
    assert "heap-buffer-overflow" in summary


def test_extract_summary_missing():
    summary = _extract_summary("no summary here\n")
    assert summary == ""
