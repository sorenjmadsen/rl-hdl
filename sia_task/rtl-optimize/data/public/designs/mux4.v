module mux4(input [7:0] a, input [7:0] b, input [7:0] c, input [7:0] d,
            input [1:0] sel, output [7:0] y);
  wire s0 = (sel == 2'd0);
  wire s1 = (sel == 2'd1);
  wire s2 = (sel == 2'd2);
  wire s3 = (sel == 2'd3);
  assign y = ({8{s0}} & a) | ({8{s1}} & b) | ({8{s2}} & c) | ({8{s3}} & d);
endmodule
