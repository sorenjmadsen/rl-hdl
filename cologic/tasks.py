"""Seed task library. Each task carries a golden reference used as the grading
oracle (see verifier.grade).

Two splits:
  TRAIN_TASKS   - what the policy trains/evals on during development.
  HELDOUT_TASKS - perturbations of the same concepts (renamed signals, changed
                  widths, recombined / inverted functions). These give the
                  *headline* number: warm-started Verilog models may have seen
                  public benchmarks, so the gain must be measured on tasks that
                  are structurally novel. held_out=True.

Difficulty is intentionally mixed so a warm-started 7B lands ~20-60% (dead-signal
guard from the RL de-risking checklist).
"""

from __future__ import annotations

from cologic.schema import Port, Task

TRAIN_TASKS: list[Task] = [
    Task(
        task_id="mux2",
        top_module="mux2",
        spec=(
            "Implement an 8-bit 2-to-1 multiplexer. When `sel` is 0, output `y` "
            "equals input `a`; when `sel` is 1, `y` equals input `b`."
        ),
        interface=[Port("a", "input", 8), Port("b", "input", 8), Port("sel", "input", 1), Port("y", "output", 8)],
        reference_rtl=(
            "module mux2(input [7:0] a, input [7:0] b, input sel, output [7:0] y);\n"
            "  assign y = sel ? b : a;\n"
            "endmodule\n"
        ),
        tags=["comb", "mux"],
    ),
    Task(
        task_id="mux4",
        top_module="mux4",
        spec=(
            "Implement an 8-bit 4-to-1 multiplexer. The 2-bit `sel` selects one of "
            "the four 8-bit inputs onto `y`: 0->a, 1->b, 2->c, 3->d."
        ),
        interface=[
            Port("a", "input", 8), Port("b", "input", 8), Port("c", "input", 8),
            Port("d", "input", 8), Port("sel", "input", 2), Port("y", "output", 8),
        ],
        reference_rtl=(
            "module mux4(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,\n"
            "            input [1:0] sel, output [7:0] y);\n"
            "  assign y = (sel == 2'd0) ? a : (sel == 2'd1) ? b : (sel == 2'd2) ? c : d;\n"
            "endmodule\n"
        ),
        tags=["comb", "mux"],
    ),
    Task(
        task_id="add4",
        top_module="add4",
        spec=(
            "Implement a 4-bit adder with carry-out. `sum` (4 bits) is the low 4 "
            "bits of `a + b`; `cout` (1 bit) is the carry out of the addition."
        ),
        interface=[Port("a", "input", 4), Port("b", "input", 4), Port("sum", "output", 4), Port("cout", "output", 1)],
        reference_rtl=(
            "module add4(input [3:0] a, input [3:0] b, output [3:0] sum, output cout);\n"
            "  assign {cout, sum} = a + b;\n"
            "endmodule\n"
        ),
        tags=["comb", "arith"],
    ),
    Task(
        task_id="cmp8",
        top_module="cmp8",
        spec=(
            "Implement an 8-bit unsigned comparator. Set `gt` when `a > b`, `eq` "
            "when `a == b`, and `lt` when `a < b`. Exactly one output is high."
        ),
        interface=[
            Port("a", "input", 8), Port("b", "input", 8),
            Port("gt", "output", 1), Port("eq", "output", 1), Port("lt", "output", 1),
        ],
        reference_rtl=(
            "module cmp8(input [7:0] a, input [7:0] b, output gt, output eq, output lt);\n"
            "  assign gt = a > b;\n  assign eq = a == b;\n  assign lt = a < b;\n"
            "endmodule\n"
        ),
        tags=["comb", "compare"],
    ),
    Task(
        task_id="alu8",
        top_module="alu8",
        spec=(
            "Implement an 8-bit ALU. The 2-bit `op` selects the operation on inputs "
            "`a` and `b`: 0 -> a+b, 1 -> a-b, 2 -> bitwise AND, 3 -> bitwise OR. "
            "Result goes to `y` (8 bits, low bits for add/sub)."
        ),
        interface=[Port("a", "input", 8), Port("b", "input", 8), Port("op", "input", 2), Port("y", "output", 8)],
        reference_rtl=(
            "module alu8(input [7:0] a, input [7:0] b, input [1:0] op, output [7:0] y);\n"
            "  assign y = (op == 2'd0) ? a + b :\n"
            "             (op == 2'd1) ? a - b :\n"
            "             (op == 2'd2) ? (a & b) : (a | b);\n"
            "endmodule\n"
        ),
        tags=["comb", "alu"],
    ),
    Task(
        task_id="dec3to8",
        top_module="dec3to8",
        spec=(
            "Implement a 3-to-8 one-hot decoder. The 3-bit `sel` chooses which one "
            "of the 8 output bits `y` is high (all others low); bit number `sel` is set."
        ),
        interface=[Port("sel", "input", 3), Port("y", "output", 8)],
        reference_rtl=(
            "module dec3to8(input [2:0] sel, output [7:0] y);\n"
            "  assign y = 8'b1 << sel;\n"
            "endmodule\n"
        ),
        tags=["comb", "decoder"],
    ),
    Task(
        task_id="popcount8",
        top_module="popcount8",
        spec=(
            "Implement a population count for an 8-bit input `a`. Output `count` "
            "(4 bits) is the number of bits in `a` that are 1 (0 through 8)."
        ),
        interface=[Port("a", "input", 8), Port("count", "output", 4)],
        reference_rtl=(
            "module popcount8(input [7:0] a, output [3:0] count);\n"
            "  assign count = a[0]+a[1]+a[2]+a[3]+a[4]+a[5]+a[6]+a[7];\n"
            "endmodule\n"
        ),
        tags=["comb", "reduction"],
    ),
    Task(
        task_id="shl8",
        top_module="shl8",
        spec=(
            "Implement an 8-bit logical left shifter. Output `y` is input `a` "
            "shifted left by `amt` (3 bits) positions, with zeros shifted in."
        ),
        interface=[Port("a", "input", 8), Port("amt", "input", 3), Port("y", "output", 8)],
        reference_rtl=(
            "module shl8(input [7:0] a, input [2:0] amt, output [7:0] y);\n"
            "  assign y = a << amt;\n"
            "endmodule\n"
        ),
        tags=["comb", "shift"],
    ),
    Task(
        task_id="absdiff8",
        top_module="absdiff8",
        spec=(
            "Implement an 8-bit unsigned absolute difference. Output `y` is the "
            "absolute value of `a - b`, i.e. the larger minus the smaller."
        ),
        interface=[Port("a", "input", 8), Port("b", "input", 8), Port("y", "output", 8)],
        reference_rtl=(
            "module absdiff8(input [7:0] a, input [7:0] b, output [7:0] y);\n"
            "  assign y = (a > b) ? (a - b) : (b - a);\n"
            "endmodule\n"
        ),
        tags=["comb", "arith"],
    ),
    Task(
        task_id="bin2gray8",
        top_module="bin2gray8",
        spec=(
            "Implement an 8-bit binary-to-Gray-code converter. Output `gray` is the "
            "Gray code of binary input `bin` (gray = bin XOR (bin >> 1))."
        ),
        interface=[Port("bin", "input", 8), Port("gray", "output", 8)],
        reference_rtl=(
            "module bin2gray8(input [7:0] bin, output [7:0] gray);\n"
            "  assign gray = bin ^ (bin >> 1);\n"
            "endmodule\n"
        ),
        tags=["comb", "encoding"],
    ),
]

HELDOUT_TASKS: list[Task] = [
    Task(  # mux2 perturbed: wider + renamed ports
        task_id="ho_mux2_w16",
        top_module="sel_mux",
        spec=(
            "Implement a 16-bit 2-to-1 multiplexer. When `s` is 0, output `out` "
            "equals input `in0`; when `s` is 1, `out` equals input `in1`."
        ),
        interface=[Port("in0", "input", 16), Port("in1", "input", 16), Port("s", "input", 1), Port("out", "output", 16)],
        reference_rtl=(
            "module sel_mux(input [15:0] in0, input [15:0] in1, input s, output [15:0] out);\n"
            "  assign out = s ? in1 : in0;\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "mux"],
    ),
    Task(  # cmp8 perturbed: narrower + renamed
        task_id="ho_cmp4",
        top_module="magnitude4",
        spec=(
            "Implement a 4-bit unsigned comparator. Set `greater` when `x > y`, "
            "`equal` when `x == y`, and `less` when `x < y`."
        ),
        interface=[
            Port("x", "input", 4), Port("y", "input", 4),
            Port("greater", "output", 1), Port("equal", "output", 1), Port("less", "output", 1),
        ],
        reference_rtl=(
            "module magnitude4(input [3:0] x, input [3:0] y, output greater, output equal, output less);\n"
            "  assign greater = x > y;\n  assign equal = x == y;\n  assign less = x < y;\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "compare"],
    ),
    Task(  # popcount perturbed: wider
        task_id="ho_popcount16",
        top_module="ones16",
        spec=(
            "Implement a population count for a 16-bit input `d`. Output `ones` "
            "(5 bits) is the number of 1 bits in `d` (0 through 16)."
        ),
        interface=[Port("d", "input", 16), Port("ones", "output", 5)],
        reference_rtl=(
            "module ones16(input [15:0] d, output [4:0] ones);\n"
            "  assign ones = $countones(d);\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "reduction"],
    ),
    Task(  # min/max recombination: train has min2-like via absdiff; here max
        task_id="ho_max2",
        top_module="pick_max",
        spec=(
            "Implement an 8-bit unsigned maximum. Output `m` is whichever of inputs "
            "`p` and `q` is larger (or either if equal)."
        ),
        interface=[Port("p", "input", 8), Port("q", "input", 8), Port("m", "output", 8)],
        reference_rtl=(
            "module pick_max(input [7:0] p, input [7:0] q, output [7:0] m);\n"
            "  assign m = (p > q) ? p : q;\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "compare"],
    ),
    Task(  # decoder perturbed: narrower
        task_id="ho_dec2to4",
        top_module="onehot2",
        spec=(
            "Implement a 2-to-4 one-hot decoder. The 2-bit `code` chooses which one "
            "of the 4 output bits `oh` is high; bit number `code` is set, others low."
        ),
        interface=[Port("code", "input", 2), Port("oh", "output", 4)],
        reference_rtl=(
            "module onehot2(input [1:0] code, output [3:0] oh);\n"
            "  assign oh = 4'b1 << code;\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "decoder"],
    ),
    Task(  # inverse of bin2gray: structurally novel vs train
        task_id="ho_gray2bin8",
        top_module="gray2bin8",
        spec=(
            "Implement an 8-bit Gray-code-to-binary converter. Output `bin` is the "
            "binary value whose Gray code is the input `gray` (the inverse of a "
            "binary-to-Gray conversion)."
        ),
        interface=[Port("gray", "input", 8), Port("bin", "output", 8)],
        reference_rtl=(
            "module gray2bin8(input [7:0] gray, output [7:0] bin);\n"
            "  assign bin = gray ^ (gray >> 1) ^ (gray >> 2) ^ (gray >> 3) ^\n"
            "               (gray >> 4) ^ (gray >> 5) ^ (gray >> 6) ^ (gray >> 7);\n"
            "endmodule\n"
        ),
        held_out=True,
        tags=["comb", "encoding"],
    ),
]

TPU_REPEATED_MATMUL_TB = r"""
// auto-generated testbench for task __TASK_ID__
module tb;
  logic clk = 0;
  logic rst_n;
  logic ena;
  logic [7:0] ui_in;
  logic [7:0] uio_in;
  wire [7:0] uo_out__c, uo_out__r;
  wire [7:0] uio_out__c, uio_out__r;
  wire [7:0] uio_oe__c, uio_oe__r;

  __DUT__ dut_c (
      .ui_in(ui_in), .uo_out(uo_out__c), .uio_in(uio_in),
      .uio_out(uio_out__c), .uio_oe(uio_oe__c), .ena(ena),
      .clk(clk), .rst_n(rst_n)
  );
  __REF__ dut_r (
      .ui_in(ui_in), .uo_out(uo_out__r), .uio_in(uio_in),
      .uio_out(uio_out__r), .uio_oe(uio_oe__r), .ena(ena),
      .clk(clk), .rst_n(rst_n)
  );

  always #5 clk = ~clk;

  integer passed = 0;
  integer total = 0;
  integer scenario;
  integer i;
  integer unused;
  logic [7:0] a [0:3];
  logic [7:0] b [0:3];

  task reset_all;
    begin
      ena = 1'b1;
      ui_in = 8'd0;
      uio_in = 8'd0;
      rst_n = 1'b0;
      repeat (5) @(posedge clk);
      rst_n = 1'b1;
      repeat (2) @(posedge clk);
    end
  endtask

  task load_elem(input integer sel, input integer idx, input [7:0] value);
    begin
      ui_in = value;
      uio_in = ((sel & 1) << 1) | ((idx & 3) << 2) | 1;
      @(posedge clk);
      #1;
      uio_in = 8'd0;
      @(posedge clk);
      #1;
    end
  endtask

  task load_current_matrices;
    begin
      for (i = 0; i < 4; i = i + 1) begin
        load_elem(0, i, a[i]);
      end
      for (i = 0; i < 4; i = i + 1) begin
        load_elem(1, i, b[i]);
      end
    end
  endtask

  task compare_outputs(input integer phase);
    begin
      repeat (3) @(posedge clk);
      for (i = 0; i < 4; i = i + 1) begin
        uio_in = ((i & 3) << 5) | (1 << 4);
        @(posedge clk);
        #1;
        total += 1;
        if (uo_out__c === uo_out__r) begin
          passed += 1;
        end else begin
          $display("MISMATCH scenario=%0d phase=%0d output=%0d candidate=%0d reference=%0d",
                   scenario, phase, i, $signed(uo_out__c), $signed(uo_out__r));
        end
        uio_in = 8'd0;
        @(posedge clk);
        #1;
      end
    end
  endtask

  initial begin
    unused = $urandom(__SEED__);
    reset_all();

    for (scenario = 0; scenario < __N_VECTORS__; scenario = scenario + 1) begin
      for (i = 0; i < 4; i = i + 1) begin
        a[i] = $urandom_range(0, 7);
        b[i] = $urandom_range(0, 7);
      end
      load_current_matrices();
      compare_outputs(0);

      for (i = 0; i < 4; i = i + 1) begin
        a[i] = $urandom_range(0, 7);
        b[i] = $urandom_range(0, 7);
      end
      load_current_matrices();
      compare_outputs(1);

      reset_all();
    end

    $display("RESULT %0d %0d", passed, total);
    $finish;
  end
endmodule
"""

TPU_REPEATED_MATMUL_REF = r"""
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
    wire [1:0] output_sel = uio_in[6:5];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a0 <= 8'sd0; a1 <= 8'sd0; a2 <= 8'sd0; a3 <= 8'sd0;
            b0 <= 8'sd0; b1 <= 8'sd0; b2 <= 8'sd0; b3 <= 8'sd0;
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
    wire signed [15:0] c01 = a0 * b1 + a1 * b3;
    wire signed [15:0] c10 = a2 * b0 + a3 * b2;
    wire signed [15:0] c11 = a2 * b1 + a3 * b3;

    reg [7:0] selected;
    always @(*) begin
        case (output_sel)
            2'd0: selected = c00[7:0];
            2'd1: selected = c01[7:0];
            2'd2: selected = c10[7:0];
            2'd3: selected = c11[7:0];
        endcase
    end

    assign uo_out = output_en ? selected : 8'd0;
    assign uio_out = {output_en, 7'b0};
    assign uio_oe = 8'b1000_0000;

    wire _unused = &{ena, uio_in[7]};
endmodule
"""

TPU_SIGNED_OUTPUT_TB = r"""
// auto-generated testbench for task __TASK_ID__
module tb;
  logic clk = 0;
  logic rst_n;
  logic ena;
  logic [7:0] ui_in;
  logic [7:0] uio_in;
  wire [7:0] uo_out__c, uo_out__r;
  wire [7:0] uio_out__c, uio_out__r;
  wire [7:0] uio_oe__c, uio_oe__r;

  __DUT__ dut_c (
      .ui_in(ui_in), .uo_out(uo_out__c), .uio_in(uio_in),
      .uio_out(uio_out__c), .uio_oe(uio_oe__c), .ena(ena),
      .clk(clk), .rst_n(rst_n)
  );
  __REF__ dut_r (
      .ui_in(ui_in), .uo_out(uo_out__r), .uio_in(uio_in),
      .uio_out(uio_out__r), .uio_oe(uio_oe__r), .ena(ena),
      .clk(clk), .rst_n(rst_n)
  );

  always #5 clk = ~clk;

  integer passed = 0;
  integer total = 0;
  integer scenario;
  integer i;
  logic [7:0] a [0:3];
  logic [7:0] b [0:3];

  task reset_all;
    begin
      ena = 1'b1;
      ui_in = 8'd0;
      uio_in = 8'd0;
      rst_n = 1'b0;
      repeat (5) @(posedge clk);
      rst_n = 1'b1;
      repeat (2) @(posedge clk);
    end
  endtask

  task load_elem(input integer sel, input integer idx, input [7:0] value);
    begin
      ui_in = value;
      uio_in = ((sel & 1) << 1) | ((idx & 3) << 2) | 1;
      @(posedge clk);
      #1;
      uio_in = 8'd0;
      @(posedge clk);
      #1;
    end
  endtask

  task load_current_matrices;
    begin
      for (i = 0; i < 4; i = i + 1) begin
        load_elem(0, i, a[i]);
      end
      for (i = 0; i < 4; i = i + 1) begin
        load_elem(1, i, b[i]);
      end
    end
  endtask

  task compare_all_outputs;
    begin
      repeat (3) @(posedge clk);
      for (i = 0; i < 4; i = i + 1) begin
        uio_in = ((i & 3) << 5) | (1 << 4);
        @(posedge clk);
        #1;
        total += 1;
        if (uo_out__c === uo_out__r) begin
          passed += 1;
        end else begin
          $display("MISMATCH scenario=%0d output=%0d candidate=%0d reference=%0d",
                   scenario, i, $signed(uo_out__c), $signed(uo_out__r));
        end
        uio_in = 8'd0;
        @(posedge clk);
        #1;
      end
    end
  endtask

  task set_scenario(input integer id);
    begin
      scenario = id;
      case (id)
        0: begin
          a[0] = 8'sd1;  a[1] = 8'sd2;  a[2] = 8'sd3;  a[3] = 8'sd4;
          b[0] = 8'sd5;  b[1] = 8'sd6;  b[2] = 8'sd7;  b[3] = 8'sd8;
        end
        1: begin
          a[0] = -8'sd3; a[1] = 8'sd4;  a[2] = 8'sd5;  a[3] = -8'sd6;
          b[0] = 8'sd7;  b[1] = -8'sd8; b[2] = 8'sd9;  b[3] = 8'sd10;
        end
        2: begin
          a[0] = -8'sd8; a[1] = -8'sd7; a[2] = 8'sd6;  a[3] = 8'sd5;
          b[0] = 8'sd4;  b[1] = -8'sd3; b[2] = -8'sd2; b[3] = 8'sd1;
        end
        default: begin
          a[0] = 8'sd12; a[1] = -8'sd11; a[2] = -8'sd10; a[3] = 8'sd9;
          b[0] = -8'sd6; b[1] = 8'sd5;   b[2] = 8'sd4;    b[3] = -8'sd3;
        end
      endcase
    end
  endtask

  initial begin
    reset_all();

    for (scenario = 0; scenario < 4; scenario = scenario + 1) begin
      set_scenario(scenario);
      load_current_matrices();
      compare_all_outputs();
      reset_all();
    end

    $display("RESULT %0d %0d", passed, total);
    $finish;
  end
endmodule
"""

NPU_INT34_TO_FP32_TB = r"""
// auto-generated testbench for task __TASK_ID__
module tb;
  logic [33:0] int34;
  wire [31:0] fp32__c, fp32__r;

  __DUT__ dut_c (.int34(int34), .fp32(fp32__c));
  __REF__ dut_r (.int34(int34), .fp32(fp32__r));

  integer passed = 0;
  integer total = 0;
  integer i;
  integer unused;

  task check(input [33:0] value);
    begin
      int34 = value;
      #1;
      total += 1;
      if (fp32__c === fp32__r) begin
        passed += 1;
      end else begin
        $display("MISMATCH int34=0x%h candidate=0x%h reference=0x%h",
                 value, fp32__c, fp32__r);
      end
      #1;
    end
  endtask

  initial begin
    unused = $urandom(__SEED__);

    check(34'h000000000); // 0
    check(34'h000000001); // 1
    check(34'h000000002); // 2
    check(34'h000000003); // 3
    check(34'h3ffffffff); // -1
    check(34'h3fffffffe); // -2
    check(34'h001000000); // 2^24
    check(34'h001000001); // rounding boundary
    check(34'h001ffffff); // rounding carry pressure
    check(34'h1ffffffff); // max positive signed 34-bit value
    check(34'h200000000); // min negative signed 34-bit value
    check(34'h2aaaaaaaa); // negative non-power-of-two pattern

    for (i = 0; i < __N_VECTORS__; i = i + 1) begin
      check({$urandom, $urandom} & 34'h3ffffffff);
    end

    $display("RESULT %0d %0d", passed, total);
    $finish;
  end
endmodule
"""

NPU_INT34_TO_FP32_REF = r"""
module npu_int34_to_fp32(
    input  wire [33:0] int34,
    output reg  [31:0] fp32
);
    integer idx;
    integer msb;
    integer shift;
    reg sign;
    reg [7:0] exponent;
    reg [22:0] mantissa;
    reg [34:0] abs_value;
    reg [34:0] rounded_value;
    reg [34:0] normalized;

    always @(*) begin
        sign = int34[33];
        abs_value = sign ? {1'b0, (~int34 + 34'd1)} : {1'b0, int34};
        exponent = 8'd0;
        mantissa = 23'd0;
        msb = 0;
        shift = 0;
        rounded_value = 35'd0;
        normalized = 35'd0;

        if (abs_value == 35'd0) begin
            fp32 = 32'h00000000;
        end else begin
            for (idx = 0; idx < 34; idx = idx + 1) begin
                if (abs_value[idx]) begin
                    msb = idx;
                end
            end

            if (msb <= 23) begin
                normalized = abs_value << (23 - msb);
                mantissa = normalized[22:0];
            end else begin
                shift = msb - 23;
                rounded_value = abs_value + (35'd1 << (shift - 1));
                if (rounded_value[msb + 1]) begin
                    msb = msb + 1;
                    shift = shift + 1;
                end
                normalized = rounded_value >> shift;
                mantissa = normalized[22:0];
            end

            exponent = 8'd127 + msb[7:0];
            fp32 = {sign, exponent, mantissa};
        end
    end
endmodule
"""

TPU_PE_ACCUM_CLEAR_TB = r"""
// auto-generated testbench for task __TASK_ID__
module tb;
  logic clk = 0;
  logic rst_n;
  logic clear;
  logic valid;
  logic signed [7:0] a;
  logic signed [7:0] b;
  wire signed [15:0] y__c;
  wire signed [15:0] y__r;

  __DUT__ dut_c (.clk(clk), .rst_n(rst_n), .clear(clear), .valid(valid), .a(a), .b(b), .y(y__c));
  __REF__ dut_r (.clk(clk), .rst_n(rst_n), .clear(clear), .valid(valid), .a(a), .b(b), .y(y__r));

  always #5 clk = ~clk;

  integer passed = 0;
  integer total = 0;
  integer step_id = 0;

  task drive(input bit do_clear, input bit do_valid, input signed [7:0] av, input signed [7:0] bv);
    begin
      @(negedge clk);
      clear = do_clear;
      valid = do_valid;
      a = av;
      b = bv;
      @(posedge clk);
      #1;
      total += 1;
      if (y__c === y__r) begin
        passed += 1;
      end else begin
        $display("MISMATCH step=%0d clear=%0d valid=%0d a=%0d b=%0d candidate=%0d reference=%0d",
                 step_id, do_clear, do_valid, av, bv, y__c, y__r);
      end
      step_id += 1;
    end
  endtask

  initial begin
    clear = 1'b0;
    valid = 1'b0;
    a = 8'sd0;
    b = 8'sd0;
    rst_n = 1'b0;
    repeat (3) @(posedge clk);
    rst_n = 1'b1;

    drive(1'b0, 1'b1,  8'sd2,   8'sd3);   // 6
    drive(1'b0, 1'b1,  8'sd4,   8'sd5);   // 26
    drive(1'b0, 1'b0,  8'sd9,   8'sd9);   // hold 26
    drive(1'b1, 1'b0,  8'sd0,   8'sd0);   // clear to 0
    drive(1'b0, 1'b1, -8'sd3,   8'sd7);   // -21
    drive(1'b0, 1'b1,  8'sd2,  -8'sd8);   // -37
    drive(1'b1, 1'b1,  8'sd6,   8'sd6);   // clear priority
    drive(1'b0, 1'b1,  8'sd12, -8'sd5);   // -60
    drive(1'b0, 1'b1, -8'sd11, -8'sd4);   // -16

    $display("RESULT %0d %0d", passed, total);
    $finish;
  end
endmodule
"""

TPU_PE_ACCUM_CLEAR_REF = r"""
module tpu_pe_accum (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              clear,
    input  wire              valid,
    input  wire signed [7:0] a,
    input  wire signed [7:0] b,
    output wire signed [15:0] y
);
    reg signed [15:0] acc;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc <= 16'sd0;
        end else if (clear) begin
            acc <= 16'sd0;
        end else if (valid) begin
            acc <= acc + (a * b);
        end
    end

    assign y = acc;
endmodule
"""

NPU_MAC_INT8_REF = r"""
module npu_mac_int8 (
    input  wire signed [7:0]  a,
    input  wire signed [7:0]  b,
    input  wire signed [17:0] acc,
    output wire signed [17:0] y
);
    assign y = acc + (a * b);
endmodule
"""

NPU_FIND_LEADING_ONE64_REF = r"""
module npu_find_leading_one64 (
    input  wire [63:0] data,
    output reg         valid,
    output reg  [5:0]  index
);
    integer i;
    always @(*) begin
        valid = |data;
        index = 6'd0;
        for (i = 0; i < 64; i = i + 1) begin
            if (data[i]) begin
                index = i[5:0];
            end
        end
    end
endmodule
"""

GRADIENT_TASKS: list[Task] = [
    Task(
        task_id="vg_tpu_repeated_matmul2x2",
        top_module="tt_um_tpu",
        spec=(
            "Implement a Tiny Tapeout-style 2x2 matrix multiply accelerator. "
            "`ui_in` carries one signed 8-bit matrix element. When `uio_in[0]` "
            "is high on a clock edge, store `ui_in` into matrix A if `uio_in[1]` "
            "is 0 or matrix B if `uio_in[1]` is 1; `uio_in[3:2]` selects the "
            "row-major element index. When `uio_in[4]` is high, output the "
            "selected low 8 bits of A*B on `uo_out`, with `uio_in[6:5]` selecting "
            "C00, C01, C10, or C11. Repeated matrix multiplies must be independent: "
            "loading a new A and B must not accumulate stale partial sums from a "
            "previous multiplication."
        ),
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
        reference_rtl=TPU_REPEATED_MATMUL_REF,
        n_vectors=16,
        seed=6,
        clocked=True,
        testbench_template=TPU_REPEATED_MATMUL_TB,
        allow_extra_modules=True,
        tags=["clocked", "verified-gradient", "tpu", "systolic-array", "matmul"],
    ),
    Task(
        task_id="vg_tpu_signed_outputs2x2",
        top_module="tt_um_tpu",
        spec=(
            "Implement a Tiny Tapeout-style 2x2 signed matrix multiply accelerator. "
            "`ui_in` carries one signed 8-bit matrix element. When `uio_in[0]` is "
            "high on a clock edge, store `ui_in` into matrix A if `uio_in[1]` is "
            "0 or matrix B if `uio_in[1]` is 1; `uio_in[3:2]` selects the row-major "
            "element index. When `uio_in[4]` is high, output the selected low 8 bits "
            "of A*B on `uo_out`, with `uio_in[6:5]` selecting C00, C01, C10, or C11. "
            "The design must treat loaded matrix elements as signed values and each "
            "output select must return the corresponding matrix product element."
        ),
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
        reference_rtl=TPU_REPEATED_MATMUL_REF,
        n_vectors=4,
        seed=8,
        clocked=True,
        testbench_template=TPU_SIGNED_OUTPUT_TB,
        allow_extra_modules=True,
        tags=["clocked", "verified-gradient", "tpu", "systolic-array", "signed", "matmul"],
    ),
    Task(
        task_id="vg_npu_int34_to_fp32",
        top_module="npu_int34_to_fp32",
        spec=(
            "Implement a combinational converter from a signed 34-bit two's "
            "complement integer `int34` to the IEEE-754 single-precision FP32 "
            "bit pattern on `fp32`. Output positive zero for input zero. For "
            "nonzero inputs, set the sign bit from the integer sign, normalize "
            "the absolute value, set the biased exponent, and produce the 23-bit "
            "fraction. When more than 24 significant bits are present, round by "
            "adding half of the discarded range before taking the fraction."
        ),
        interface=[Port("int34", "input", 34), Port("fp32", "output", 32)],
        reference_rtl=NPU_INT34_TO_FP32_REF,
        n_vectors=96,
        seed=64,
        testbench_template=NPU_INT34_TO_FP32_TB,
        tags=["comb", "verified-gradient", "npu", "mac", "fp32", "conversion"],
    ),
    Task(
        task_id="vg_tpu_pe_accum_clear",
        top_module="tpu_pe_accum",
        spec=(
            "Implement a clocked signed 8-bit multiply-accumulate processing "
            "element for a TPU-style systolic array. On reset, the accumulator "
            "is zero. On each rising clock edge, `clear` has priority and sets "
            "`y` to zero. Otherwise, when `valid` is high, accumulate `a * b` "
            "into the signed 16-bit output `y`; when `valid` is low, hold the "
            "previous value."
        ),
        interface=[
            Port("clk", "input", 1),
            Port("rst_n", "input", 1),
            Port("clear", "input", 1),
            Port("valid", "input", 1),
            Port("a", "input", 8),
            Port("b", "input", 8),
            Port("y", "output", 16),
        ],
        reference_rtl=TPU_PE_ACCUM_CLEAR_REF,
        n_vectors=9,
        seed=6,
        clocked=True,
        testbench_template=TPU_PE_ACCUM_CLEAR_TB,
        tags=["clocked", "verified-gradient", "tpu", "systolic-array", "mac", "clear"],
    ),
    Task(
        task_id="vg_npu_mac_int8",
        top_module="npu_mac_int8",
        spec=(
            "Implement a combinational signed INT8 multiply-accumulate lane for "
            "an NPU MAC array. Treat `a`, `b`, and `acc` as signed two's-complement "
            "values. Output signed 18-bit `y = acc + a * b`."
        ),
        interface=[
            Port("a", "input", 8),
            Port("b", "input", 8),
            Port("acc", "input", 18),
            Port("y", "output", 18),
        ],
        reference_rtl=NPU_MAC_INT8_REF,
        n_vectors=96,
        seed=67,
        tags=["comb", "verified-gradient", "npu", "mac", "int8"],
    ),
    Task(
        task_id="vg_npu_find_leading_one64",
        top_module="npu_find_leading_one64",
        spec=(
            "Implement a combinational leading-one detector for a 64-bit NPU "
            "normalization path. Set `valid` when any bit of `data` is one. "
            "When valid, `index` is the index of the most-significant set bit; "
            "when `data` is zero, `valid` is zero and `index` is zero."
        ),
        interface=[
            Port("data", "input", 64),
            Port("valid", "output", 1),
            Port("index", "output", 6),
        ],
        reference_rtl=NPU_FIND_LEADING_ONE64_REF,
        n_vectors=128,
        seed=56,
        tags=["comb", "verified-gradient", "npu", "normalization", "leading-one"],
    ),
]

SEED_TASKS: list[Task] = TRAIN_TASKS + HELDOUT_TASKS + GRADIENT_TASKS
BY_ID = {t.task_id: t for t in SEED_TASKS}
