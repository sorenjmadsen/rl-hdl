module share_mul(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,
                 input s, output [15:0] y);
  wire [15:0] prod_ab = a * b;
  wire [15:0] prod_cd = c * d;
  assign y = s ? prod_ab : prod_cd;
endmodule
