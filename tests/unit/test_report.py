"""Unit tests for report aggregation and severity grading."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import RET_SUCCESS, RET_WARNING, RET_CRITICAL
from core.report import Report, TestResult


def test_empty_report():
    r = Report("test")
    assert r.worst_code == RET_SUCCESS
    assert r.overall_status == "PASS"


def test_all_pass():
    r = Report("test")
    r.add(TestResult(name="a", status="PASS", return_code=RET_SUCCESS))
    r.add(TestResult(name="b", status="PASS", return_code=RET_SUCCESS))
    assert r.worst_code == RET_SUCCESS
    assert r.overall_status == "PASS"


def test_worst_code_wins():
    r = Report("test")
    r.add(TestResult(name="a", status="PASS", return_code=RET_SUCCESS))
    r.add(TestResult(name="b", status="WARNING", return_code=RET_WARNING))
    r.add(TestResult(name="c", status="FAIL", return_code=RET_CRITICAL))
    assert r.worst_code == RET_CRITICAL
    assert r.overall_status == "FAIL"


def test_warning_without_critical():
    r = Report("test")
    r.add(TestResult(name="a", status="PASS", return_code=RET_SUCCESS))
    r.add(TestResult(name="b", status="WARNING", return_code=RET_WARNING))
    assert r.worst_code == RET_WARNING
    assert r.overall_status == "WARNING"


def test_save_json(tmp_path):
    r = Report("test")
    r.add(TestResult(name="bench", status="PASS", return_code=RET_SUCCESS, message="ok"))
    r.add(TestResult(name="shader", status="FAIL", return_code=RET_CRITICAL, message="2 errors"))
    out = tmp_path / "report.json"
    r.save_json(out)

    with open(out) as f:
        data = json.load(f)
    assert data["project"] == "test"
    assert data["overall"] == "FAIL"
    assert data["return_code"] == RET_CRITICAL
    assert len(data["tests"]) == 2
    assert data["tests"][0]["name"] == "bench"
    assert data["tests"][1]["status"] == "FAIL"
