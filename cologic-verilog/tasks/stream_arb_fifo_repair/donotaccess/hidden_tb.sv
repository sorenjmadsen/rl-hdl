module stream_arb_fifo_hidden_tb;
    localparam int WIDTH = 8;
    localparam int DEPTH = 8;
    localparam int COUNT_WIDTH = $clog2(DEPTH + 1);

    logic clk_i = 1'b0;
    logic reset_i;
    logic [WIDTH-1:0] data0_i;
    logic valid0_i;
    logic ready0_o;
    logic [WIDTH-1:0] data1_i;
    logic valid1_i;
    logic ready1_o;
    logic valid_o;
    logic [WIDTH-1:0] data_o;
    logic yumi_i;
    logic [COUNT_WIDTH-1:0] count_o;
    logic selected_lane_o;

    int scenario_errors;
    int scenarios_passed = 0;
    int scenarios_total = 0;
    int model_head;
    int model_tail;
    int model_count;
    bit model_rr_next;
    logic [WIDTH-1:0] model_q [0:255];

    stream_arb_fifo #(
        .width_p(WIDTH),
        .depth_p(DEPTH)
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

    always #5 clk_i = ~clk_i;

    function automatic logic [WIDTH-1:0] model_front;
        model_front = model_q[model_head % DEPTH];
    endfunction

    task automatic check_bit(input logic actual, input logic expected, input string label);
        if (actual !== expected) begin
            $display("CHECK_FAIL %s expected=%0b actual=%0b", label, expected, actual);
            scenario_errors++;
        end
    endtask

    task automatic check_count(input int expected, input string label);
        if (count_o !== COUNT_WIDTH'(expected)) begin
            $display("CHECK_FAIL %s expected=%0d actual=%0d", label, expected, count_o);
            scenario_errors++;
        end
    endtask

    task automatic check_byte(input logic [WIDTH-1:0] actual,
                              input logic [WIDTH-1:0] expected,
                              input string label);
        if (actual !== expected) begin
            $display("CHECK_FAIL %s expected=0x%0h actual=0x%0h", label, expected, actual);
            scenario_errors++;
        end
    endtask

    task automatic reset_model;
        begin
            model_head = 0;
            model_tail = 0;
            model_count = 0;
            model_rr_next = 1'b0;
        end
    endtask

    task automatic reset_dut;
        begin
            reset_i = 1'b1;
            valid0_i = 1'b0;
            valid1_i = 1'b0;
            yumi_i = 1'b0;
            data0_i = '0;
            data1_i = '0;
            repeat (3) @(posedge clk_i);
            #1;
            reset_i = 1'b0;
            reset_model();
            check_bit(valid_o, 1'b0, "reset_valid");
            check_count(0, "reset_count");
            @(negedge clk_i);
        end
    endtask

    task automatic finish_scenario(input string name);
        begin
            scenarios_total++;
            if (scenario_errors == 0) begin
                scenarios_passed++;
                $display("SCENARIO %s PASS", name);
            end else begin
                $display("SCENARIO %s FAIL errors=%0d", name, scenario_errors);
            end
        end
    endtask

    task automatic drive_cycle(input logic v0,
                               input logic [WIDTH-1:0] d0,
                               input logic v1,
                               input logic [WIDTH-1:0] d1,
                               input logic y,
                               input string label);
        logic exp_valid;
        logic exp_can_accept;
        logic exp_ready0;
        logic exp_ready1;
        logic exp_push0;
        logic exp_push1;
        logic exp_pop;
        begin
            valid0_i = v0;
            data0_i = d0;
            valid1_i = v1;
            data1_i = d1;
            yumi_i = y;
            #1;

            exp_valid = (model_count != 0);
            exp_pop = y && exp_valid;
            exp_can_accept = (model_count < DEPTH) || exp_pop;
            exp_ready0 = 1'b0;
            exp_ready1 = 1'b0;
            if (exp_can_accept) begin
                if (v0 && v1) begin
                    exp_ready0 = !model_rr_next;
                    exp_ready1 = model_rr_next;
                end else if (v0) begin
                    exp_ready0 = 1'b1;
                end else if (v1) begin
                    exp_ready1 = 1'b1;
                end
            end
            exp_push0 = exp_ready0 && v0;
            exp_push1 = exp_ready1 && v1;

            check_bit(valid_o, exp_valid, {label, "_valid"});
            check_count(model_count, {label, "_count"});
            check_bit(ready0_o, exp_ready0, {label, "_ready0"});
            check_bit(ready1_o, exp_ready1, {label, "_ready1"});
            if (exp_valid) begin
                check_byte(data_o, model_front(), {label, "_front"});
            end

            @(posedge clk_i);
            #1;

            if (exp_push0) begin
                model_q[model_tail % DEPTH] = d0;
            end else if (exp_push1) begin
                model_q[model_tail % DEPTH] = d1;
            end
            if (exp_pop) begin
                model_head++;
                model_count--;
            end
            if (exp_push0 || exp_push1) begin
                model_tail++;
                model_count++;
                model_rr_next = exp_push0;
            end
            check_count(model_count, {label, "_post_count"});
            @(negedge clk_i);
        end
    endtask

    task automatic scenario_lane1_only;
        begin
            scenario_errors = 0;
            reset_dut();
            drive_cycle(1'b0, 8'h00, 1'b1, 8'h81, 1'b0, "lane1_push0");
            drive_cycle(1'b0, 8'h00, 1'b1, 8'h82, 1'b0, "lane1_push1");
            drive_cycle(1'b0, 8'h00, 1'b1, 8'h83, 1'b0, "lane1_push2");
            drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "lane1_pop0");
            drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "lane1_pop1");
            drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "lane1_pop2");
            finish_scenario("lane1_only_order");
        end
    endtask

    task automatic scenario_round_robin;
        begin
            scenario_errors = 0;
            reset_dut();
            for (int i = 0; i < 6; i++) begin
                drive_cycle(1'b1, WIDTH'(8'h10 + i), 1'b1, WIDTH'(8'ha0 + i),
                            1'b0, "rr_push");
            end
            for (int i = 0; i < 6; i++) begin
                drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "rr_pop");
            end
            finish_scenario("round_robin_contention");
        end
    endtask

    task automatic scenario_full_pop_push;
        begin
            scenario_errors = 0;
            reset_dut();
            for (int i = 0; i < DEPTH; i++) begin
                drive_cycle(1'b1, WIDTH'(8'h30 + i), 1'b0, 8'h00, 1'b0, "fill");
            end
            drive_cycle(1'b0, 8'h00, 1'b1, 8'hee, 1'b1, "full_pop_push_lane1");
            for (int i = 0; i < DEPTH; i++) begin
                drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "drain_after_full");
            end
            finish_scenario("full_accepts_after_pop");
        end
    endtask

    task automatic scenario_reset_flush;
        begin
            scenario_errors = 0;
            reset_dut();
            drive_cycle(1'b1, 8'h44, 1'b0, 8'h00, 1'b0, "pre_reset_lane0");
            drive_cycle(1'b0, 8'h00, 1'b1, 8'h99, 1'b0, "pre_reset_lane1");
            reset_dut();
            drive_cycle(1'b0, 8'h00, 1'b1, 8'h55, 1'b0, "post_reset_lane1");
            drive_cycle(1'b0, 8'h00, 1'b0, 8'h00, 1'b1, "post_reset_pop");
            finish_scenario("reset_flushes_and_restarts");
        end
    endtask

    initial begin
        scenario_lane1_only();
        scenario_round_robin();
        scenario_full_pop_push();
        scenario_reset_flush();
        $display("SUMMARY hidden %0d/%0d", scenarios_passed, scenarios_total);
        $finish;
    end
endmodule
