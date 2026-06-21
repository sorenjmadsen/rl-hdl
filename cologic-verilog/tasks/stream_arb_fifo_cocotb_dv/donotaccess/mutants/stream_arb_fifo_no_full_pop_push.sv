module stream_arb_fifo #(
    parameter int width_p = 8,
    parameter int depth_p = 8,
    parameter int count_width_lp = $clog2(depth_p + 1),
    parameter int addr_width_lp = $clog2(depth_p)
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
    localparam logic [count_width_lp-1:0] depth_count_lp = count_width_lp'(depth_p);
    localparam logic [addr_width_lp-1:0] last_addr_lp = addr_width_lp'(depth_p - 1);

    logic [width_p-1:0] mem [0:depth_p-1];
    logic [addr_width_lp-1:0] wr_ptr_r;
    logic [addr_width_lp-1:0] rd_ptr_r;
    logic [count_width_lp-1:0] count_r;
    logic rr_next_r;
    logic can_accept;
    logic push0;
    logic push1;
    logic push_fire;
    logic pop_fire;

    assign count_o = count_r;
    assign valid_o = (count_r != '0);
    assign data_o = mem[rd_ptr_r];
    assign pop_fire = yumi_i && valid_o;
    assign can_accept = (count_r < depth_count_lp);

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
                ready1_o = 1'b1;
                selected_lane_o = 1'b1;
            end
        end
    end

    assign push0 = ready0_o && valid0_i;
    assign push1 = ready1_o && valid1_i;
    assign push_fire = push0 || push1;

    function automatic logic [addr_width_lp-1:0] incr_ptr(
        input logic [addr_width_lp-1:0] ptr
    );
        if (ptr == last_addr_lp) begin
            incr_ptr = '0;
        end else begin
            incr_ptr = ptr + addr_width_lp'(1);
        end
    endfunction

    always_ff @(posedge clk_i) begin
        if (reset_i) begin
            wr_ptr_r <= '0;
            rd_ptr_r <= '0;
            count_r <= '0;
            rr_next_r <= 1'b0;
        end else begin
            if (push_fire) begin
                mem[wr_ptr_r] <= push0 ? data0_i : data1_i;
                wr_ptr_r <= incr_ptr(wr_ptr_r);
                rr_next_r <= push0;
            end

            if (pop_fire) begin
                rd_ptr_r <= incr_ptr(rd_ptr_r);
            end

            unique case ({push_fire, pop_fire})
                2'b10: count_r <= count_r + count_width_lp'(1);
                2'b01: count_r <= count_r - count_width_lp'(1);
                default: count_r <= count_r;
            endcase
        end
    end
endmodule
