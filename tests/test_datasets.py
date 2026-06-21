"""VerilogEval adapter: parsing + a poison-guard self-grade on a sample."""

import shutil

import pytest

from cologic.datasets.verilogeval import is_combinational, load, parse_ports
from cologic.verifier import grade


def test_parse_ports_basic():
    ref = "module RefModule (\n input [7:0] a,\n input sel,\n output logic [7:0] out\n);\n"
    ports = parse_ports(ref)
    assert [(p.name, p.direction, p.width) for p in ports] == [
        ("a", "input", 8), ("sel", "input", 1), ("out", "output", 8),
    ]


def test_parse_ports_rejects_inout():
    assert parse_ports("module RefModule (\n inout x\n);") is None


def test_is_combinational():
    assert is_combinational("assign y = a & b;")
    assert not is_combinational("always @(posedge clk) q <= d;")


def test_load_returns_tasks():
    tasks = load()
    assert len(tasks) > 50
    t = tasks[0]
    assert t.top_module == "TopModule" and t.prompt_is_complete
    assert "module TopModule" in t.reference_rtl


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_sample_goldens_self_grade():
    # A handful of converted goldens must reproduce themselves (1.0); a malformed
    # conversion would surface here before it reached training.
    for t in load()[:6]:
        r = grade(t.reference_rtl, t)
        assert r.reward == pytest.approx(1.0), f"{t.task_id}: {r.info}"
