// Scaffold-fill stimulus for mac_fp32_converter (int34 -> fp32, 2-stage pipe).
//
// The harness owns the differential testbench shell: the free-running clk, the
// dual __DUT__/__REF__ instantiation, the port declarations, the `rlhdl_sample`
// comparator (checks o_data of candidate vs reference), and the `RESULT` line.
// This file supplies module-scope helpers plus `task stimulus;`.
//
// Protocol (from the upstream tb_mac_fp32_converter): hold the datatype/exp
// inputs in integer mode (MAC_DATATYPE_I9, exp=0), drive i_intdata, then walk a
// value through the pipeline by asserting i_pipe_en[0] (stage-0 capture) for one
// edge and i_pipe_en[1] (stage-1 capture) on the next, after which o_data is the
// fp32 encoding for that value. Candidate and reference are sampled there, so
// both must preserve the 2-cycle latency and the conversion result.

  integer scenario;
  integer unused;
  reg [33:0] vec;

  // Push one signed-34-bit value through the 2-stage pipeline and compare.
  task drive_one(input [33:0] value);
    begin
      i_intdata = value;
      i_pipe_en = 2'b01;        // stage-0 capture
      @(posedge clk); #1;
      i_pipe_en = 2'b10;        // stage-1 capture
      @(posedge clk); #1;
      rlhdl_sample;             // o_data valid for `value`
      i_pipe_en = 2'b00;
      @(posedge clk); #1;
    end
  endtask

  task stimulus;
    begin
      unused = $urandom(__SEED__);
      // Integer mode, matching the upstream bench.
      i_ifm_datatype = 3'd0;    // MAC_DATATYPE_I9
      i_wfm_datatype = 3'd0;
      i_exp          = 6'd0;
      i_pipe_en      = 2'b00;
      i_intdata      = 34'd0;
      repeat (3) @(posedge clk);

      // Directed corners: 0, +1, +2, -1.
      drive_one(34'h000000000);
      drive_one(34'h000000001);
      drive_one(34'h000000002);
      drive_one(34'h3FFFFFFFF);

      // Random 34-bit signed integers (full range incl. sign bit).
      for (scenario = 0; scenario < __N_VECTORS__; scenario = scenario + 1) begin
        vec = {$urandom, $urandom};
        drive_one(vec);
      end
    end
  endtask
