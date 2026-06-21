module stream_arb_fifo_formal_top;
    localparam int width_p = 8;
    localparam int depth_p = 4;
    localparam int count_width_lp = $clog2(depth_p + 1);
    localparam int addr_width_lp = $clog2(depth_p);

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

    logic [width_p-1:0] model_mem [0:depth_p-1];
    logic [addr_width_lp-1:0] model_wr_ptr;
    logic [addr_width_lp-1:0] model_rd_ptr;
    logic [count_width_lp-1:0] model_count;
    logic rr_pref_model;
    logic saw_wrap;
    logic past_valid;

    wire push0 = valid0_i && ready0_o;
    wire push1 = valid1_i && ready1_o;
    wire push_fire = push0 || push1;
    wire pop_fire = valid_o && yumi_i;
    wire [width_p-1:0] push_data = push0 ? data0_i : data1_i;
    wire can_accept = (count_o < count_width_lp'(depth_p)) || pop_fire;

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

    function automatic logic [addr_width_lp-1:0] incr_ptr(
        input logic [addr_width_lp-1:0] ptr
    );
        if (ptr == addr_width_lp'(depth_p - 1)) begin
            incr_ptr = '0;
        end else begin
            incr_ptr = ptr + addr_width_lp'(1);
        end
    endfunction

    always @(posedge clk_i) begin
        if (reset_i) begin
            model_wr_ptr <= '0;
            model_rd_ptr <= '0;
            model_count <= '0;
            rr_pref_model <= 1'b0;
            saw_wrap <= 1'b0;
        end else begin
            if (push_fire) begin
                model_mem[model_wr_ptr] <= push_data;
                model_wr_ptr <= incr_ptr(model_wr_ptr);
                rr_pref_model <= push0 ? 1'b1 : 1'b0;
                if (model_wr_ptr == addr_width_lp'(depth_p - 1)) begin
                    saw_wrap <= 1'b1;
                end
            end

            if (pop_fire) begin
                model_rd_ptr <= incr_ptr(model_rd_ptr);
            end

            unique case ({push_fire, pop_fire})
                2'b10: model_count <= model_count + count_width_lp'(1);
                2'b01: model_count <= model_count - count_width_lp'(1);
                default: model_count <= model_count;
            endcase
        end
    end

    always @(posedge clk_i) begin
        if (past_valid && $past(reset_i)) begin
            assert(count_o == '0);
            assert(!valid_o);
        end else if (past_valid && !reset_i) begin
            assert(count_o == model_count);
            assert(count_o <= count_width_lp'(depth_p));
            assert(valid_o == (model_count != '0));

            if (model_count != '0) begin
                assert(data_o == model_mem[model_rd_ptr]);
            end

            if (!can_accept) begin
                assert(!ready0_o);
                assert(!ready1_o);
            end

            if (can_accept && valid0_i && !valid1_i) begin
                assert(ready0_o);
                assert(!ready1_o);
                assert(!selected_lane_o);
            end

            if (can_accept && !valid0_i && valid1_i) begin
                assert(!ready0_o);
                assert(ready1_o);
                assert(selected_lane_o);
            end

            if (can_accept && valid0_i && valid1_i) begin
                assert(ready0_o == !rr_pref_model);
                assert(ready1_o == rr_pref_model);
                assert(selected_lane_o == rr_pref_model);
            end

            if (
                count_o == count_width_lp'(depth_p)
                && valid_o
                && yumi_i
                && (valid0_i || valid1_i)
            ) begin
                assert(ready0_o || ready1_o);
            end
        end
    end

    always @(posedge clk_i) begin
        cover(past_valid && !reset_i && valid1_i && ready1_o);
        cover(past_valid && !reset_i && valid0_i && valid1_i && ready0_o);
        cover(past_valid && !reset_i && valid0_i && valid1_i && ready1_o);
        cover(
            past_valid
            && !reset_i
            && count_o == count_width_lp'(depth_p)
            && valid_o
            && yumi_i
            && (valid0_i || valid1_i)
            && (ready0_o || ready1_o)
        );
        cover(past_valid && !reset_i && saw_wrap && valid_o && data_o == model_mem[model_rd_ptr]);
    end
endmodule
