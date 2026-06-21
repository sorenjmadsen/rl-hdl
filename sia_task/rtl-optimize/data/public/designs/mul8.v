module mul8(input [7:0] a, input [7:0] b, output [15:0] p);
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
