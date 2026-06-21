"""Interface parsing + Task construction for uploaded Verilog (cologic.upload)."""

from __future__ import annotations

import json
import shutil

import pytest

from cologic.upload import (
    build_clocked_testbench_template,
    is_clocked,
    parse_interface,
    resolve_top,
    task_from_manifest_entry,
    task_from_rtl,
    task_from_upload,
    write_upload_dataset,
)


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


# ── multi-file / scaffold-fill ingestion (the upload flow) ─────────────────────

_HELPER = "module inc(input [7:0] x, output [7:0] y);\n  assign y = x + 8'd1;\nendmodule\n"
_TOP = ("module acc(input clk, input rst_n, input [7:0] x, output reg [7:0] y);\n"
        "  wire [7:0] xn;\n  inc u_inc(.x(x), .y(xn));\n"
        "  always @(posedge clk or negedge rst_n)\n"
        "    if (!rst_n) y <= 8'd0; else y <= y + xn;\n"
        "endmodule\n")

_STIMULUS = """
task stimulus;
  integer i;
  begin
    rst_n = 0; x = 0;
    @(posedge clk); #1;
    rst_n = 1;
    for (i = 0; i < 16; i = i + 1) begin
      x = i[7:0];
      @(posedge clk); #1;
      rlhdl_sample;
    end
  end
endtask
"""


def test_resolve_top_picks_uninstantiated_module():
    rtl = _HELPER + "\n" + _TOP
    assert resolve_top(rtl) == "acc"  # `inc` is instantiated by `acc`


def test_scaffold_template_requires_stimulus_task_and_clock():
    iface = parse_interface(_TOP, "acc")[1]
    with pytest.raises(ValueError, match="task stimulus"):
        build_clocked_testbench_template(iface, "// no entry point here")
    combo = [p for p in iface if p.name != "clk"]  # drop the clock
    with pytest.raises(ValueError, match="clock port"):
        build_clocked_testbench_template(combo, _STIMULUS)


def test_clocked_upload_requires_stimulus():
    with pytest.raises(ValueError, match="clocked design"):
        task_from_upload({"acc.v": _TOP, "inc.v": _HELPER}, prompt="shrink it")


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_scaffold_fill_clocked_upload_self_grades_equivalent():
    """The clocked upload flow end-to-end: many files + scaffold stimulus -> a Task
    that grades the reference against itself as equivalent over real simulation."""
    from cologic.grader import grade

    task = task_from_upload(
        {"acc.v": _TOP, "inc.v": _HELPER},
        prompt="Optimize this accumulator for gate count.",
        stimulus=_STIMULUS,
        task_id="acc_upload",
    )
    assert task.top_module == "acc"
    assert task.clocked and task.testbench_template and task.allow_extra_modules
    r = grade(task.reference_rtl, task)
    assert r.info["equivalent"] is True
    assert r.info["eq_total"] == 16 and r.info["eq_passed"] == 16


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_scaffold_fill_catches_non_equivalent_rewrite():
    """A behaviour-changing 'optimization' must fail the differential check."""
    from cologic.grader import grade

    task = task_from_upload(
        {"acc.v": _TOP, "inc.v": _HELPER},
        prompt="Optimize this accumulator for gate count.",
        stimulus=_STIMULUS,
    )
    broken = (_HELPER + "\n" + _TOP).replace("y <= y + xn;", "y <= y + xn + 8'd1;")
    r = grade(broken, task)
    assert r.info["equivalent"] is False


# ── manifest loader (shared by the SIA target agent + evaluate.py) ─────────────


def test_manifest_entry_combinational(tmp_path):
    (tmp_path / "designs").mkdir()
    (tmp_path / "designs" / "add5.v").write_text(
        "module add5(input [3:0] a, input [3:0] b, output [4:0] s);\n"
        "  assign s = a + b;\nendmodule\n"
    )
    entry = {"id": "add5", "file": "designs/add5.v", "n_vectors": 64, "seed": 2}
    task = task_from_manifest_entry(entry, tmp_path)
    assert task.task_id == "add5" and task.top_module == "add5"
    assert not task.clocked and task.testbench_template is None
    assert task.n_vectors == 64 and task.seed == 2


def test_manifest_entry_clocked_uses_files_and_stimulus(tmp_path):
    """The TPU-shaped path: a multi-file clocked design + a scaffold stimulus file,
    loaded identically to how the SIA agent + evaluate.py will load it."""
    (tmp_path / "acc.v").write_text(_TOP)
    (tmp_path / "inc.v").write_text(_HELPER)
    (tmp_path / "acc_stim.sv").write_text(_STIMULUS)
    entry = {
        "id": "acc",
        "files": ["acc.v", "inc.v"],
        "stimulus_file": "acc_stim.sv",
        "top_module": "acc",
    }
    task = task_from_manifest_entry(entry, tmp_path)
    assert task.clocked and task.testbench_template and task.allow_extra_modules
    assert "__DUT__" in task.testbench_template  # placeholders intact for build_testbench
    assert task.top_module == "acc"


def test_write_dataset_round_trips_through_loader(tmp_path):
    """Module 2 contract: the SIA dataset writer + the manifest loader are inverses,
    so an uploaded clocked design lands as a Task the agent + evaluate.py can grade."""
    upload = {
        "id": "acc",
        "files": {"acc.v": _TOP, "inc.v": _HELPER},
        "stimulus": _STIMULUS,
        "top_module": "acc",
        "prompt": "Shrink the accumulator.",
        "n_vectors": 32,
        "seed": 3,
    }
    public = tmp_path / "data" / "public"
    public.mkdir(parents=True)
    entry = write_upload_dataset(public, upload)
    assert entry["files"] == ["designs/acc.v", "designs/inc.v"]
    assert entry["stimulus_file"] == "designs/acc_stim.sv"
    assert entry["spec"] == "Shrink the accumulator."

    manifest = json.loads((public / "manifest.json").read_text())
    task = task_from_manifest_entry(manifest["designs"][0], public)
    assert task.task_id == "acc" and task.top_module == "acc"
    assert task.clocked and task.testbench_template and task.seed == 3
    assert task.spec == "Shrink the accumulator."
