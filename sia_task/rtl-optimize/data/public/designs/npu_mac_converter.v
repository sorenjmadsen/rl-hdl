// Self-contained baseline: int34 -> IEEE-754 fp32 converter from the
// universal_NPU-CNN_accelerator MAC datapath (gold ec3b1ea, PR #64).
//
// Reconstructed as ONE self-contained design for the SIA optimize task: the
// SystemVerilog package/enum (`mac_pkg`) is inlined as localparams, the standalone
// `find_leading_one` helper is inlined (the grader synthesizes only the top, so
// the design must be self-contained), and the clock port is renamed `clk` so the
// scaffold harness free-runs it. Behaviour is preserved: a 2-stage
// pipeline (gated by i_pipe_en) that takes a signed 34-bit integer and emits its
// fp32 encoding. Datatype/exp inputs select the bias mode; the stimulus exercises
// integer mode (MAC_DATATYPE_I9) like the upstream bench.

module mac_fp32_converter (
    input  wire        clk,
    input  wire [2:0]  i_ifm_datatype,
    input  wire [2:0]  i_wfm_datatype,
    input  wire [5:0]  i_exp,
    input  wire [33:0] i_intdata,
    input  wire [1:0]  i_pipe_en,
    output wire [31:0] o_data
);
    localparam W_I_INT     = 34;
    localparam EXP         = 8;
    localparam BIAS_FP32   = 127;
    localparam BIAS_FP16   = 15;
    localparam BIAS_FP8    = 7;
    localparam BIAS_ADD_FP = 8;
    // Inlined mac_pkg::mac_datatype enum.
    localparam DT_I9   = 3'd0;
    localparam DT_FP8  = 3'd1;
    localparam DT_FP16 = 3'd2;
    localparam DT_FP32 = 3'd3;

    // ---- bias of exponent ----
    wire [EXP-1:0] bias_i, bias_w, bias_add, bias_total;
    wire [EXP-1:0] exp_biased, exp_is_int;

    assign bias_i = (i_ifm_datatype == DT_FP16) ? BIAS_FP16
                  : (i_ifm_datatype == DT_FP8 ) ? BIAS_FP8 : 0;
    assign bias_w = (i_wfm_datatype == DT_FP16) ? BIAS_FP16
                  : (i_wfm_datatype == DT_FP8 ) ? BIAS_FP8 : 0;
    assign bias_add   = (i_ifm_datatype == DT_I9) ? (W_I_INT-1) : BIAS_ADD_FP;
    assign bias_total = BIAS_FP32 - bias_i - bias_w + bias_add;

    assign exp_is_int = (i_ifm_datatype == DT_I9) ? 0 : i_exp;
    assign exp_biased = exp_is_int + bias_total;

    // ---- abs ----
    wire [W_I_INT-1:0] abs_v;
    wire is_zero;
    assign abs_v   = i_intdata[W_I_INT-1] ? (~i_intdata + 1'b1) : i_intdata;
    assign is_zero = (i_intdata == 0);

    // ---- leading one over the low 32 bits (inlined find_leading_one, clz-style) ----
    wire [31:0] flo_in = abs_v[W_I_INT-3:0];
    wire [15:0] flo_level0;
    wire [7:0]  flo_level1;
    wire [3:0]  flo_level2;
    wire [1:0]  flo_level3;

    genvar gi;
    generate
        for (gi = 0; gi < 16; gi = gi + 1) assign flo_level0[gi] = flo_in[gi*2]    | flo_in[gi*2+1];
        for (gi = 0; gi < 8;  gi = gi + 1) assign flo_level1[gi] = flo_level0[gi*2] | flo_level0[gi*2+1];
        for (gi = 0; gi < 4;  gi = gi + 1) assign flo_level2[gi] = flo_level1[gi*2] | flo_level1[gi*2+1];
        for (gi = 0; gi < 2;  gi = gi + 1) assign flo_level3[gi] = flo_level2[gi*2] | flo_level2[gi*2+1];
    endgenerate

    wire [4:0] flo_pre;
    assign flo_pre[4] = flo_level3[1];
    assign flo_pre[3] = flo_level2[{flo_pre[4], 1'b1}];
    assign flo_pre[2] = flo_level1[{flo_pre[4], flo_pre[3], 1'b1}];
    assign flo_pre[1] = flo_level0[{flo_pre[4], flo_pre[3], flo_pre[2], 1'b1}];
    assign flo_pre[0] = flo_in[{flo_pre[4], flo_pre[3], flo_pre[2], flo_pre[1], 1'b1}];

    wire [4:0] pre_leading_one = ~flo_pre;

    // ---- pipeline 0 ----
    reg r_sign;
    reg [EXP-1:0]     r_exp_biased;
    reg [W_I_INT-1:0] r_abs;
    reg r_is_zero;
    reg [4:0] r_pre_leading_one;
    always @(posedge clk) begin
        if (i_pipe_en[0]) begin
            r_sign            <= i_intdata[W_I_INT-1];
            r_exp_biased      <= exp_biased;
            r_abs             <= abs_v;
            r_is_zero         <= is_zero;
            r_pre_leading_one <= pre_leading_one;
        end
    end

    // ---- leading one (resolve top two bits) ----
    reg [5:0] leading_one;
    always @(*) begin
        case (r_abs[W_I_INT-1:W_I_INT-2])
            2'b00:   leading_one = r_pre_leading_one + 2;
            2'b01:   leading_one = 1;
            default: leading_one = 0;
        endcase
    end

    // ---- shift ----
    wire [W_I_INT-1:0] shifted_mant;
    assign shifted_mant = r_abs << (leading_one + 1);

    // ---- pipeline 1 ----
    reg r2_sign;
    reg [EXP-1:0]     r2_exp_biased;
    reg r2_is_zero;
    reg [W_I_INT-1:0] r_shifted_mant;
    always @(posedge clk) begin
        if (i_pipe_en[1]) begin
            r2_sign        <= r_sign;
            r2_exp_biased  <= r_exp_biased - leading_one;
            r2_is_zero     <= r_is_zero;
            r_shifted_mant <= shifted_mant;
        end
    end

    // ---- mantissa + round-to-nearest-even ----
    wire [22:0] mant;
    wire guard, round_b, sticky, lsb;
    assign mant    = r_shifted_mant[W_I_INT-1 -: 23];
    assign lsb     = r_shifted_mant[W_I_INT-23];
    assign guard   = r_shifted_mant[W_I_INT-24];
    assign round_b = r_shifted_mant[W_I_INT-25];
    assign sticky  = |r_shifted_mant[W_I_INT-26:0];

    reg [EXP-1:0] fp32_exp;
    reg [22:0]    fp32_mant;
    reg is_overflow;
    always @(*) begin
        is_overflow = 0;
        fp32_exp    = 0;
        fp32_mant   = 0;
        if (r2_is_zero) begin
            fp32_exp  = 0;
            fp32_mant = 0;
        end else begin
            if (guard & (lsb | guard | round_b | sticky)) begin
                {is_overflow, fp32_mant} = mant + 1'b1;
            end else begin
                fp32_mant = mant;
            end
            fp32_exp = r2_exp_biased + is_overflow;
        end
    end

    assign o_data = {r2_sign, fp32_exp, fp32_mant};
endmodule
