module tt_um_tpu (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    reg signed [7:0] a0, a1, a2, a3;
    reg signed [7:0] b0, b1, b2, b3;

    wire load_en = uio_in[0];
    wire load_sel_b = uio_in[1];
    wire [1:0] load_index = uio_in[3:2];
    wire output_en = uio_in[4];
    wire [1:0] output_sel = uio_in[6:5];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a0 <= 8'sd0; a1 <= 8'sd0; a2 <= 8'sd0; a3 <= 8'sd0;
            b0 <= 8'sd0; b1 <= 8'sd0; b2 <= 8'sd0; b3 <= 8'sd0;
        end else if (load_en) begin
            if (!load_sel_b) begin
                case (load_index)
                    2'd0: a0 <= ui_in;
                    2'd1: a1 <= ui_in;
                    2'd2: a2 <= ui_in;
                    2'd3: a3 <= ui_in;
                endcase
            end else begin
                case (load_index)
                    2'd0: b0 <= ui_in;
                    2'd1: b1 <= ui_in;
                    2'd2: b2 <= ui_in;
                    2'd3: b3 <= ui_in;
                endcase
            end
        end
    end

    wire signed [15:0] c00 = a0 * b0 + a1 * b2;
    wire signed [15:0] c01 = a0 * b1 + a1 * b3;
    wire signed [15:0] c10 = a2 * b0 + a3 * b2;
    wire signed [15:0] c11 = a2 * b1 + a3 * b3;

    reg [7:0] selected;
    always @(*) begin
        case (output_sel)
            2'd0: selected = c00[7:0];
            2'd1: selected = c01[7:0];
            2'd2: selected = c10[7:0];
            2'd3: selected = c11[7:0];
        endcase
    end

    assign uo_out = output_en ? selected : 8'd0;
    assign uio_out = {output_en, 7'b0};
    assign uio_oe = 8'b1000_0000;

    wire _unused = &{ena, uio_in[7]};
endmodule
