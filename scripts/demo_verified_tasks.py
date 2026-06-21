"""Demo the native verified-gradient TPU tasks.

This is intentionally small and local: it grades each converted TPU task's
reference design, then grades a known broken implementation that matches the
upstream bug shape the task was distilled from.

Usage:
    uv run python scripts/demo_verified_tasks.py
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from rl_hdl import grade
from rl_hdl.tasks import BY_ID


STALE_ACCUMULATOR = """
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


COLLAPSED_OUTPUT_SELECT = """
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


@dataclass(frozen=True)
class DemoCase:
    task_id: str
    label: str
    completion: str
    should_pass: bool


def run_case(case: DemoCase) -> tuple[DemoCase, float, str, int, int]:
    task = BY_ID[case.task_id]
    result = grade(case.completion, task, timeout=90.0)
    return (
        case,
        result.reward,
        result.info.get("stage", "unknown"),
        int(result.info.get("passed", 0)),
        int(result.info.get("total", 0)),
    )


def main() -> int:
    if shutil.which("verilator") is None:
        print("verilator not found on PATH; install Verilator before running this demo.", file=sys.stderr)
        return 2

    cases = [
        DemoCase(
            task_id="vg_tpu_repeated_matmul2x2",
            label="reference: repeated matmul",
            completion=BY_ID["vg_tpu_repeated_matmul2x2"].reference_rtl,
            should_pass=True,
        ),
        DemoCase(
            task_id="vg_tpu_repeated_matmul2x2",
            label="broken: stale accumulator",
            completion=STALE_ACCUMULATOR,
            should_pass=False,
        ),
        DemoCase(
            task_id="vg_tpu_signed_outputs2x2",
            label="reference: signed outputs",
            completion=BY_ID["vg_tpu_signed_outputs2x2"].reference_rtl,
            should_pass=True,
        ),
        DemoCase(
            task_id="vg_tpu_signed_outputs2x2",
            label="broken: collapsed output select",
            completion=COLLAPSED_OUTPUT_SELECT,
            should_pass=False,
        ),
    ]

    rows = [run_case(case) for case in cases]

    print("Verified-gradient TPU task demo")
    print()
    print(f"{'case':36} {'task':30} {'stage':14} {'reward':>8} {'matches':>12}")
    print("-" * 106)
    for case, reward, stage, passed, total in rows:
        print(f"{case.label:36} {case.task_id:30} {stage:14} {reward:8.3f} {passed:5d}/{total:<5d}")

    failures = []
    for case, reward, stage, passed, total in rows:
        passed_full = stage == "graded" and total > 0 and passed == total and reward == 1.0
        passed_partial = stage == "graded" and total > 0 and passed < total and 0.0 < reward < 1.0
        if case.should_pass and not passed_full:
            failures.append(f"{case.label}: expected full reward")
        if not case.should_pass and not passed_partial:
            failures.append(f"{case.label}: expected partial reward")

    if failures:
        print()
        print("Demo failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
