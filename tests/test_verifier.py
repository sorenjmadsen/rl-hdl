"""End-to-end checks that the Verilator-grounded reward behaves: correct designs
score 1.0, broken-but-compiling designs score the compile floor, garbage scores 0.
"""

import shutil

import pytest

from cologic import grade
from cologic.tasks import BY_ID, SEED_TASKS
from cologic.verifier import COMPILE_ERROR_REWARD, COMPILE_FLOOR

pytestmark = pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")

MUX = BY_ID["mux2"]


@pytest.mark.parametrize("task", SEED_TASKS, ids=[t.task_id for t in SEED_TASKS])
def test_golden_reference_self_grades_full(task):
    """Every task's own reference, fed as the completion, must score 1.0.

    This is the oracle's smoke test: a malformed reference (bad width, typo,
    wrong logic) would surface here before it ever poisons training.
    """
    r = grade(task.reference_rtl, task)
    assert r.info["stage"] == "graded", f"{task.task_id}: {r.info.get('log', '')[:400]}"
    assert r.reward == pytest.approx(1.0), f"{task.task_id}: {r.info}"


def test_correct_design_scores_full():
    good = """```verilog
module mux2(input [7:0] a, input [7:0] b, input sel, output [7:0] y);
  assign y = sel ? b : a;
endmodule
```"""
    r = grade(good, MUX)
    assert r.info["stage"] == "graded"
    assert r.reward == pytest.approx(1.0)
    assert r.info["passed"] == r.info["total"] > 0


def test_wrong_but_compiling_scores_floor():
    # Always outputs a, ignoring sel: compiles, fails ~half the vectors.
    wrong = """module mux2(input [7:0] a, input [7:0] b, input sel, output [7:0] y);
  assign y = a;
endmodule"""
    r = grade(wrong, MUX)
    assert r.info["stage"] == "graded"
    assert COMPILE_FLOOR <= r.reward < 1.0


def test_renamed_module_still_binds():
    # Model used a different module name; grader should rename it to the top.
    renamed = """module my_mux(input [7:0] a, input [7:0] b, input sel, output [7:0] y);
  assign y = sel ? b : a;
endmodule"""
    r = grade(renamed, MUX)
    assert r.reward == pytest.approx(1.0)


def test_syntax_error_scores_compile_error():
    broken = """module mux2(input [7:0] a, input [7:0] b, input sel, output [7:0] y);
  assign y = sel ? b : a   // missing semicolon
endmodule"""
    r = grade(broken, MUX)
    assert r.info["stage"] == "compile_error"
    assert r.reward == COMPILE_ERROR_REWARD


def test_no_module_scores_zero():
    r = grade("Sure! Here is how a multiplexer works conceptually...", MUX)
    assert r.info["stage"] == "no_module"
    assert r.reward == 0.0


def test_tpu_repeated_matmul_catches_stale_accumulator():
    task = BY_ID["vg_tpu_repeated_matmul2x2"]
    stale_accumulator = """
module tt_um_tpu (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    reg signed [7:0] a0, a1, a2, a3;
    reg signed [7:0] b0, b1, b2, b3;
    reg signed [15:0] c0, c1, c2, c3;
    reg computed;

    wire load_en = uio_in[0];
    wire load_sel_b = uio_in[1];
    wire [1:0] load_index = uio_in[3:2];
    wire output_en = uio_in[4];
    wire [1:0] output_sel = uio_in[6:5];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a0 <= 0; a1 <= 0; a2 <= 0; a3 <= 0;
            b0 <= 0; b1 <= 0; b2 <= 0; b3 <= 0;
            c0 <= 0; c1 <= 0; c2 <= 0; c3 <= 0;
            computed <= 0;
        end else begin
            if (load_en) begin
                computed <= 0;
                if (!load_sel_b) begin
                    case (load_index)
                        2'd0: a0 <= ui_in;
                        2'd1: a1 <= ui_in;
                        2'd2: a2 <= ui_in;
                        2'd3: a3 <= ui_in;
                    endcase
                end else begin
                    case (load_index)
                        2'd0: b0 <= ui_in;
                        2'd1: b1 <= ui_in;
                        2'd2: b2 <= ui_in;
                        2'd3: b3 <= ui_in;
                    endcase
                end
            end else if (output_en && !computed) begin
                c0 <= c0 + a0 * b0 + a1 * b2;
                c1 <= c1 + a0 * b1 + a1 * b3;
                c2 <= c2 + a2 * b0 + a3 * b2;
                c3 <= c3 + a2 * b1 + a3 * b3;
                computed <= 1;
            end
        end
    end

    assign uo_out = !output_en ? 8'd0 :
                    output_sel == 2'd0 ? c0[7:0] :
                    output_sel == 2'd1 ? c1[7:0] :
                    output_sel == 2'd2 ? c2[7:0] : c3[7:0];
    assign uio_out = {output_en, 7'b0};
    assign uio_oe = 8'b1000_0000;

    wire _unused = &{ena, uio_in[7]};
endmodule
"""
    r = grade(stale_accumulator, task, timeout=90.0)
    assert r.info["stage"] == "graded", r.info.get("log", "")[:400]
    assert COMPILE_FLOOR <= r.reward < 1.0
    assert r.info["passed"] < r.info["total"]


def test_tpu_signed_outputs_catches_collapsed_output_select():
    task = BY_ID["vg_tpu_signed_outputs2x2"]
    collapsed_output_select = """
module tt_um_tpu (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    reg signed [7:0] a0, a1, a2, a3;
    reg signed [7:0] b0, b1, b2, b3;

    wire load_en = uio_in[0];
    wire load_sel_b = uio_in[1];
    wire [1:0] load_index = uio_in[3:2];
    wire output_en = uio_in[4];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a0 <= 0; a1 <= 0; a2 <= 0; a3 <= 0;
            b0 <= 0; b1 <= 0; b2 <= 0; b3 <= 0;
        end else if (load_en) begin
            if (!load_sel_b) begin
                case (load_index)
                    2'd0: a0 <= ui_in;
                    2'd1: a1 <= ui_in;
                    2'd2: a2 <= ui_in;
                    2'd3: a3 <= ui_in;
                endcase
            end else begin
                case (load_index)
                    2'd0: b0 <= ui_in;
                    2'd1: b1 <= ui_in;
                    2'd2: b2 <= ui_in;
                    2'd3: b3 <= ui_in;
                endcase
            end
        end
    end

    wire signed [15:0] c00 = a0 * b0 + a1 * b2;

    assign uo_out = output_en ? c00[7:0] : 8'd0;
    assign uio_out = {output_en, 7'b0};
    assign uio_oe = 8'b1000_0000;

    wire _unused = &{ena, uio_in[7:5], a2, a3, b1, b3};
endmodule
"""
    r = grade(collapsed_output_select, task, timeout=90.0)
    assert r.info["stage"] == "graded", r.info.get("log", "")[:400]
    assert COMPILE_FLOOR <= r.reward < 1.0
    assert r.info["passed"] < r.info["total"]
