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

OPT_TASKS: list[Task] = [mul8, mux4, popcount8]
BY_ID = {t.task_id: t for t in OPT_TASKS}

