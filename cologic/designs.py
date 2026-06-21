"""Optimization task library (§9 floor).

An optimization task reuses the v1 `Task` schema, but its `reference_rtl` plays a
new role: it is the *correct-but-unoptimized baseline to beat*, not a spec oracle
for generation. The grader treats it as both the equivalence oracle AND the area
baseline. `tags` carries headroom metadata so task curation can be audited.

`mul8` is the seed floor design: a naive unrolled shift-add 8x8 multiplier. It is
correct but verbose, and carries real structural headroom. Alongside it we keep
two hand-written rewrites used to prove the equivalence gate BEFORE any model is
involved:

  MUL8_GOOD   - a behavioral `a*b`; equivalent, lets the synthesizer pick the
                best multiplier (the win we want the optimizer to discover).
  MUL8_BROKEN - the same shift-add structure with one partial product dropped;
                subtly wrong, so the gate must reject it on some input vectors.
"""

from __future__ import annotations

from cologic.schema import Port, Task

# Naive baseline: each partial product spelled out, then summed. Correct, bloated.
MUL8_BASELINE = """module mul8(input [7:0] a, input [7:0] b, output [15:0] p);
  wire [15:0] pp0 = b[0] ? ({8'b0, a} << 0) : 16'b0;
  wire [15:0] pp1 = b[1] ? ({8'b0, a} << 1) : 16'b0;
  wire [15:0] pp2 = b[2] ? ({8'b0, a} << 2) : 16'b0;
  wire [15:0] pp3 = b[3] ? ({8'b0, a} << 3) : 16'b0;
  wire [15:0] pp4 = b[4] ? ({8'b0, a} << 4) : 16'b0;
  wire [15:0] pp5 = b[5] ? ({8'b0, a} << 5) : 16'b0;
  wire [15:0] pp6 = b[6] ? ({8'b0, a} << 6) : 16'b0;
  wire [15:0] pp7 = b[7] ? ({8'b0, a} << 7) : 16'b0;
  assign p = pp0 + pp1 + pp2 + pp3 + pp4 + pp5 + pp6 + pp7;
endmodule
"""

# Equivalent rewrite — the optimization the policy should converge on.
MUL8_GOOD = """module mul8(input [7:0] a, input [7:0] b, output [15:0] p);
  assign p = a * b;
endmodule
"""

# Subtly broken: pp3 is dropped from the sum. Wrong whenever b[3] is set.
MUL8_BROKEN = """module mul8(input [7:0] a, input [7:0] b, output [15:0] p);
  wire [15:0] pp0 = b[0] ? ({8'b0, a} << 0) : 16'b0;
  wire [15:0] pp1 = b[1] ? ({8'b0, a} << 1) : 16'b0;
  wire [15:0] pp2 = b[2] ? ({8'b0, a} << 2) : 16'b0;
  wire [15:0] pp4 = b[4] ? ({8'b0, a} << 4) : 16'b0;
  wire [15:0] pp5 = b[5] ? ({8'b0, a} << 5) : 16'b0;
  wire [15:0] pp6 = b[6] ? ({8'b0, a} << 6) : 16'b0;
  wire [15:0] pp7 = b[7] ? ({8'b0, a} << 7) : 16'b0;
  assign p = pp0 + pp1 + pp2 + pp4 + pp5 + pp6 + pp7;
endmodule
"""

mul8 = Task(
    task_id="opt_mul8",
    top_module="mul8",
    spec="Optimize this 8x8 unsigned multiplier for gate count while preserving its function.",
    interface=[Port("a", "input", 8), Port("b", "input", 8), Port("p", "output", 16)],
    reference_rtl=MUL8_BASELINE,
    n_vectors=256,  # dense enough that a dropped partial product is reliably caught
    tags=["comb", "arith", "headroom:resource-share"],
)

# --- mux4: a verbose one-hot AND/OR datapath; the win is collapsing to a select. ---
MUX4_BASELINE = """module mux4(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,
            input [1:0] sel, output [7:0] y);
  wire s0 = (sel == 2'd0);
  wire s1 = (sel == 2'd1);
  wire s2 = (sel == 2'd2);
  wire s3 = (sel == 2'd3);
  assign y = ({8{s0}} & a) | ({8{s1}} & b) | ({8{s2}} & c) | ({8{s3}} & d);
endmodule
"""

mux4 = Task(
    task_id="opt_mux4",
    top_module="mux4",
    spec="Optimize this 4-to-1 multiplexer for gate count while preserving its function.",
    interface=[
        Port("a", "input", 8), Port("b", "input", 8), Port("c", "input", 8),
        Port("d", "input", 8), Port("sel", "input", 2), Port("y", "output", 8),
    ],
    reference_rtl=MUX4_BASELINE,
    n_vectors=256,
    tags=["comb", "mux", "headroom:select-collapse"],
)

# --- popcount8: a serial accumulate loop; the win is a balanced adder tree. ---
POPCOUNT8_BASELINE = """module popcount8(input [7:0] a, output reg [3:0] count);
  integer i;
  always @(*) begin
    count = 0;
    for (i = 0; i < 8; i = i + 1)
      count = count + a[i];
  end
endmodule
"""

popcount8 = Task(
    task_id="opt_popcount8",
    top_module="popcount8",
    spec="Optimize this 8-bit population count for gate count while preserving its function.",
    interface=[Port("a", "input", 8), Port("count", "output", 4)],
    reference_rtl=POPCOUNT8_BASELINE,
    n_vectors=256,
    tags=["comb", "reduction", "headroom:adder-tree"],
)

# --- share_mul: an unshared datapath. The baseline instantiates TWO multipliers
# but only one product is ever selected; the win is to share one multiplier and
# mux its operands. This headroom SURVIVES full Yosys synth (the `share` pass is
# not in the default recipe and abc won't merge $mul), so it's ~+49% real, and
# it's purely combinational — the existing equivalence gate handles it. This is
# the brief's canonical "resource-share / unshared datapath" optimization. ---
SHARE_MUL_BASELINE = """module share_mul(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,
                 input s, output [15:0] y);
  wire [15:0] prod_ab = a * b;
  wire [15:0] prod_cd = c * d;
  assign y = s ? prod_ab : prod_cd;
endmodule
"""

share_mul = Task(
    task_id="opt_share_mul",
    top_module="share_mul",
    spec="Optimize this datapath for gate count while preserving its function "
         "(it selects one of two 8x8 products).",
    interface=[
        Port("a", "input", 8), Port("b", "input", 8), Port("c", "input", 8),
        Port("d", "input", 8), Port("s", "input", 1), Port("y", "output", 16),
    ],
    reference_rtl=SHARE_MUL_BASELINE,
    n_vectors=256,
    tags=["comb", "arith", "headroom:resource-share"],
)

# The optimization the agent should discover (≈49% smaller, provably equivalent):
#   assign y = (s ? a : c) * (s ? b : d);
SHARE_MUL_SHARED = """module share_mul(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,
                 input s, output [15:0] y);
  assign y = (s ? a : c) * (s ? b : d);
endmodule
"""

# --- share_add: HELD-OUT cousin of share_mul (unshared adders instead of multipliers).
# Same resource-sharing optimization, structurally novel vs the public set — used to
# measure whether an evolved harness GENERALIZES, not just memorizes the train designs. ---
SHARE_ADD_BASELINE = """module share_add(input [15:0] a, input [15:0] b, input [15:0] c, input [15:0] d,
                 input s, output [15:0] y);
  wire [15:0] sum_ab = a + b;
  wire [15:0] sum_cd = c + d;
  assign y = s ? sum_ab : sum_cd;
endmodule
"""

share_add = Task(
    task_id="opt_share_add",
    top_module="share_add",
    spec="Optimize this datapath for gate count while preserving its function "
         "(it selects one of two 16-bit sums).",
    interface=[
        Port("a", "input", 16), Port("b", "input", 16), Port("c", "input", 16),
        Port("d", "input", 16), Port("s", "input", 1), Port("y", "output", 16),
    ],
    reference_rtl=SHARE_ADD_BASELINE,
    n_vectors=256,
    held_out=True,
    tags=["comb", "arith", "headroom:resource-share"],
)

OPT_TASKS: list[Task] = [mul8, mux4, popcount8, share_mul, share_add]
TRAIN_OPT_TASKS: list[Task] = [t for t in OPT_TASKS if not t.held_out]
HELDOUT_OPT_TASKS: list[Task] = [t for t in OPT_TASKS if t.held_out]
BY_ID = {t.task_id: t for t in OPT_TASKS}


# ─────────────────────────────────────────────────────────────────────────────
# SERIOUS BENCHMARK — real external RTL, answer NOT supplied by us.
#
# Everything above is small, combinational, and (importantly) hand-written here,
# so its optimization ceiling is bounded by what we already know to write. That
# cannot demonstrate the project's core claim: that the loop exceeds the bare LLM.
#
# `tpu_matmul` instead points the optimizer at the REAL `tt_um_tpu` — a 2x2 signed
# systolic matrix-multiply accelerator from the open-source repo `YashKarthik/tpu`
# (a verified gradient; provenance in data/verified_gradients.jsonl). We did not
# author it. Its baseline spells out EIGHT signed 8x8 multipliers
#   c00=a0*b0+a1*b2  c01=a0*b1+a1*b3  c10=a2*b0+a3*b2  c11=a2*b1+a3*b3
# yet only ONE byte (output_sel of c00..c11) is observable per cycle — a genuine
# unshared datapath with large, synth-surviving headroom whose optimal sharing is
# a real engineering problem, not one we encode here.
#
# This is a CLOCKED task, so it grades through the equivalence-testbench-template
# path (candidate vs. reference co-simulated under the same stimulus) rather than
# the auto-generated combinational testbench. We reuse the real candidate-vs-ref
# testbench already written for the verified-gradient correctness task.
#
# Note the role swap vs. the v1 correctness task `vg_tpu_repeated_matmul2x2`: there
# the model GENERATES `tt_um_tpu` from a spec and the RTL is the oracle; here the
# RTL is the BASELINE TO BEAT and the only reward is "equivalent to it AND smaller"
# (cologic.grader). We deliberately ship NO reference-optimal rewrite — the tooling
# decides what counts, so the benchmark can measure optimizations we don't know.
# ─────────────────────────────────────────────────────────────────────────────
from cologic.tasks import TPU_REPEATED_MATMUL_REF, TPU_REPEATED_MATMUL_TB  # noqa: E402

TPU_MATMUL_BASELINE = TPU_REPEATED_MATMUL_REF

# Subtly broken "optimization": C11 reads b2 instead of b3 in its second product.
# Equivalent on most stimuli; wrong only when output_sel==3 (C11) and b2 != b3.
# Used ONLY to prove the equivalence gate catches a bad rewrite — never as a target.
TPU_MATMUL_BROKEN = TPU_REPEATED_MATMUL_REF.replace(
    "wire signed [15:0] c11 = a2 * b1 + a3 * b3;",
    "wire signed [15:0] c11 = a2 * b1 + a3 * b2;",
)

tpu_matmul = Task(
    task_id="opt_tpu_matmul2x2",
    top_module="tt_um_tpu",
    spec="Optimize this 2x2 signed matrix-multiply accelerator for gate count while "
         "preserving its exact cycle-accurate I/O behaviour (it loads matrices A and B "
         "and outputs a selected element of A*B).",
    interface=[
        Port("ui_in", "input", 8),
        Port("uo_out", "output", 8),
        Port("uio_in", "input", 8),
        Port("uio_out", "output", 8),
        Port("uio_oe", "output", 8),
        Port("ena", "input", 1),
        Port("clk", "input", 1),
        Port("rst_n", "input", 1),
    ],
    reference_rtl=TPU_MATMUL_BASELINE,
    n_vectors=64,  # 8 output comparisons per scenario -> dense clocked equivalence check
    seed=6,
    clocked=True,
    testbench_template=TPU_REPEATED_MATMUL_TB,
    allow_extra_modules=True,  # an optimized rewrite may factor out submodules
    tags=["clocked", "arith", "tpu", "systolic-array", "headroom:resource-share", "serious"],
)

# Clocked optimization tasks grade through a testbench template, so they are kept
# OUT of OPT_TASKS (which feeds the combinational upload/manifest flow). The
# measurement harness consumes this list directly.
CLOCKED_OPT_TASKS: list[Task] = [tpu_matmul]

