"""Interface parsing + Task construction for uploaded Verilog (cologic.upload)."""

from __future__ import annotations

import shutil

import pytest

from cologic.upload import is_clocked, parse_interface, task_from_rtl


def test_parse_ansi_widths_and_output_reg():
    rtl = ("module popcount8(input [7:0] a, output reg [3:0] count);\n"
           "  always @(*) count = a[0]+a[1]+a[2]+a[3]+a[4]+a[5]+a[6]+a[7];\n"
           "endmodule\n")
    top, ports = parse_interface(rtl)
    assert top == "popcount8"
    assert [(p.name, p.direction, p.width) for p in ports] == [
        ("a", "input", 8), ("count", "output", 4),
    ]


def test_grouped_ports_inherit_direction_and_width():
    rtl = "module m(input [7:0] a, b, output y);\n  assign y = ^(a & b);\nendmodule\n"
    _, ports = parse_interface(rtl)
    assert [(p.name, p.direction, p.width) for p in ports] == [
        ("a", "input", 8), ("b", "input", 8), ("y", "output", 1),
    ]


def test_clocked_is_detected():
    rtl = "module ff(input clk, input d, output reg q);\n  always @(posedge clk) q <= d;\nendmodule\n"
    _, ports = parse_interface(rtl)
    assert is_clocked(ports)


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_task_from_raw_rtl_self_grades_equivalent():
    """The upload path: build a gradeable Task from RTL alone and self-grade it."""
    from cologic.grader import grade

    rtl = "module add5(input [3:0] a, input [3:0] b, output [4:0] s);\n  assign s = a + b;\nendmodule\n"
    task = task_from_rtl(rtl, task_id="add5")
    assert task.top_module == "add5"
    r = grade(rtl, task)
    assert r.info["equivalent"] is True
