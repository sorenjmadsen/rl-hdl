module share_add(input [15:0] a, input [15:0] b, input [15:0] c, input [15:0] d,
                 input s, output [15:0] y);
  wire [15:0] sum_ab = a + b;
  wire [15:0] sum_cd = c + d;
  assign y = s ? sum_ab : sum_cd;
endmodule
