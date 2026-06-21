module stream_arb_fifo_visible_tb;
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
    int errors = 0;

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

    task automatic check_bit(input logic actual, input logic expected, input string label);
        if (actual !== expected) begin
            $display("VISIBLE FAIL %s expected=%0b actual=%0b", label, expected, actual);
            errors++;
        end
    endtask

    task automatic check_byte(input logic [WIDTH-1:0] actual,
                              input logic [WIDTH-1:0] expected,
                              input string label);
        if (actual !== expected) begin
            $display("VISIBLE FAIL %s expected=0x%0h actual=0x%0h", label, expected, actual);
            errors++;
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
            @(negedge clk_i);
        end
    endtask

    task automatic push_lane1(input logic [WIDTH-1:0] value);
        begin
            valid0_i = 1'b0;
            valid1_i = 1'b1;
            data1_i = value;
            yumi_i = 1'b0;
            #1;
            check_bit(ready1_o, 1'b1, "lane1_ready");
            @(posedge clk_i);
            #1;
            valid1_i = 1'b0;
            @(negedge clk_i);
        end
    endtask

    task automatic pop_expect(input logic [WIDTH-1:0] expected);
        begin
            valid0_i = 1'b0;
            valid1_i = 1'b0;
            yumi_i = 1'b1;
            #1;
            check_bit(valid_o, 1'b1, "output_valid");
            check_byte(data_o, expected, "output_data");
            @(posedge clk_i);
            #1;
            yumi_i = 1'b0;
            @(negedge clk_i);
        end
    endtask

    initial begin
        reset_dut();

        push_lane1(8'h81);
        push_lane1(8'h82);
        pop_expect(8'h81);
        pop_expect(8'h82);

        valid0_i = 1'b1;
        valid1_i = 1'b1;
        data0_i = 8'h10;
        data1_i = 8'ha0;
        #1;
        check_bit(ready0_o, 1'b1, "first_contention_lane0_ready");
        check_bit(ready1_o, 1'b0, "first_contention_lane1_waits");
        @(posedge clk_i);
        #1;
        @(negedge clk_i);
        #1;
        check_bit(ready0_o, 1'b0, "second_contention_lane0_waits");
        check_bit(ready1_o, 1'b1, "second_contention_lane1_ready");

        if (errors == 0) begin
            $display("VISIBLE PASS");
        end else begin
            $display("VISIBLE FAIL errors=%0d", errors);
            $fatal(1);
        end

        $finish;
    end
endmodule
