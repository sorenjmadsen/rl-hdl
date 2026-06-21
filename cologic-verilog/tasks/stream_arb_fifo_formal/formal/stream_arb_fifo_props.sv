module stream_arb_fifo_formal_top;
    localparam int width_p = 8;
    localparam int depth_p = 4;
    localparam int count_width_lp = $clog2(depth_p + 1);

    logic clk_i;
    logic reset_i;

    (* anyseq *) logic [width_p-1:0] data0_i;
    (* anyseq *) logic [width_p-1:0] data1_i;
    (* anyseq *) logic valid0_i;
    (* anyseq *) logic valid1_i;
    (* anyseq *) logic yumi_i;

    logic ready0_o;
    logic ready1_o;
    logic valid_o;
    logic [width_p-1:0] data_o;
    logic [count_width_lp-1:0] count_o;
    logic selected_lane_o;
    logic past_valid;

    initial begin
        reset_i = 1'b1;
        past_valid = 1'b0;
    end

    always @(posedge clk_i) begin
        reset_i <= 1'b0;
        past_valid <= 1'b1;
    end

    stream_arb_fifo #(
        .width_p(width_p),
        .depth_p(depth_p)
    ) dut (
        .clk_i(clk_i),
        .reset_i(reset_i),
        .data0_i(data0_i),
        .valid0_i(valid0_i),
        .ready0_o(ready0_o),
        .data1_i(data1_i),
        .valid1_i(valid1_i),
        .ready1_o(ready1_o),
        .valid_o(valid_o),
        .data_o(data_o),
        .yumi_i(yumi_i),
        .count_o(count_o),
        .selected_lane_o(selected_lane_o)
    );

    always @(posedge clk_i) begin
        if (past_valid && $past(reset_i)) begin
            assert(count_o == '0);
            assert(!valid_o);
        end else if (past_valid && !reset_i) begin
            assert(count_o <= count_width_lp'(depth_p));
        end
    end

    always @(posedge clk_i) begin
        cover(past_valid && !reset_i && valid0_i && ready0_o);
    end

endmodule
