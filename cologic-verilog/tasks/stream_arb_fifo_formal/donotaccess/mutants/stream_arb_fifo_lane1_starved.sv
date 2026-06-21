module stream_arb_fifo #(
    parameter int width_p = 8,
    parameter int depth_p = 8,
    parameter int count_width_lp = $clog2(depth_p + 1),
    parameter int bsg_depth_lp = depth_p + 1
) (
    input  logic                    clk_i,
    input  logic                    reset_i,

    input  logic [width_p-1:0]      data0_i,
    input  logic                    valid0_i,
    output logic                    ready0_o,

    input  logic [width_p-1:0]      data1_i,
    input  logic                    valid1_i,
    output logic                    ready1_o,

    output logic                    valid_o,
    output logic [width_p-1:0]      data_o,
    input  logic                    yumi_i,

    output logic [count_width_lp-1:0] count_o,
    output logic                    selected_lane_o
);
    logic [count_width_lp-1:0] count_r;
    logic rr_next_r;
    logic can_accept;
    logic push0;
    logic push1;
    logic push_fire;
    logic pop_fire;
    logic fifo_ready_lo;
    logic fifo_valid_lo;
    logic [width_p-1:0] fifo_data_li;

    assign count_o = count_r;
    assign valid_o = fifo_valid_lo;
    assign pop_fire = yumi_i && valid_o;

    // One spare internal entry permits exposed-full pop+push cycles.
    assign can_accept = ((count_r < count_width_lp'(depth_p)) || pop_fire) && fifo_ready_lo;

    always_comb begin
        ready0_o = 1'b0;
        ready1_o = 1'b0;
        selected_lane_o = 1'b0;
        if (can_accept) begin
            if (valid0_i && valid1_i) begin
                ready0_o = !rr_next_r;
                ready1_o = rr_next_r;
                selected_lane_o = rr_next_r;
            end else if (valid0_i) begin
                ready0_o = 1'b1;
                selected_lane_o = 1'b0;
            end else if (valid1_i) begin
                ready1_o = 1'b0;
                selected_lane_o = 1'b1;
            end
        end
    end

    assign push0 = ready0_o && valid0_i;
    assign push1 = ready1_o && valid1_i;
    assign push_fire = push0 || push1;
    assign fifo_data_li = push0 ? data0_i : data1_i;

    bsg_fifo_1r1w_small #(
        .width_p(width_p),
        .els_p(bsg_depth_lp),
        .ready_THEN_valid_p(0)
    ) fifo (
        .clk_i(clk_i),
        .reset_i(reset_i),
        .v_i(push_fire),
        .ready_param_o(fifo_ready_lo),
        .data_i(fifo_data_li),
        .v_o(fifo_valid_lo),
        .data_o(data_o),
        .yumi_i(pop_fire)
    );

    always_ff @(posedge clk_i) begin
        if (reset_i) begin
            count_r <= '0;
            rr_next_r <= 1'b0;
        end else begin
            if (push_fire) begin
                rr_next_r <= push0;
            end

            unique case ({push_fire, pop_fire})
                2'b10: count_r <= count_r + count_width_lp'(1);
                2'b01: count_r <= count_r - count_width_lp'(1);
                default: count_r <= count_r;
            endcase
        end
    end
endmodule
