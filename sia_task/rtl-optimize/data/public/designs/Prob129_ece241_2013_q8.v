// Baseline to beat: ece241 2013 q8 — a Mealy FSM that detects the input
// sequence and asserts z. Correct but spelled out as an explicit 3-state machine;
// the optimization target is gate count while preserving exact cycle-accurate I/O.
// (Sourced from the VerilogEval iccad2023 reference, renamed to a single
// self-contained top so the grader synthesizes exactly one design.)
module Prob129 (
  input clk,
  input aresetn,
  input x,
  output reg z
);

  parameter S=0, S1=1, S10=2;
  reg[1:0] state, next;

  always@(posedge clk, negedge aresetn)
    if (!aresetn)
      state <= S;
    else
      state <= next;

  always_comb begin
    case (state)
      S: next = x ? S1 : S;
      S1: next = x ? S1 : S10;
      S10: next = x ? S1 : S;
      default: next = 'x;
    endcase
  end

  always_comb begin
    case (state)
      S: z = 0;
      S1: z = 0;
      S10: z = x;
      default: z = 'x;
    endcase
  end

endmodule
