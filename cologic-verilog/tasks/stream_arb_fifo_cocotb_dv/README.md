# Stream FIFO CocoTB Verification

This is a reference HDL task for the Verilog Tasks RFP. It exercises the
Verification track, repair/debug variant.

The DUT is a correct two-lane ready/valid/yumi stream FIFO wrapper in
[`rtl/stream_arb_fifo.sv`](rtl/stream_arb_fifo.sv). The wrapper composes a
vendored subset of BaseJump STL under
[`vendor/basejump_stl`](vendor/basejump_stl), using `bsg_fifo_1r1w_small` for
the storage primitive while keeping task-specific arbitration and exposed FIFO
semantics in the wrapper. The wrapper exposes `depth_p` entries but instantiates
the BaseJump FIFO with one spare internal entry so it can support same-cycle
pop plus push when the exposed FIFO is full. The agent edits the CocoTB testbench in
[`dv/cocotb/test_stream_arb_fifo.py`](dv/cocotb/test_stream_arb_fifo.py).
The starter testbench is intentionally weak: it checks reset and one lane-0
push/pop path, but it does not verify the harder protocol cases. A complete
solution should pass on the golden DUT, fail on hidden mutant DUTs, and mark
coverage for the required scenarios.

## Vendored Library

This task vendors the minimum BaseJump STL files needed to compile the DUT.
Do not fetch libraries at runtime. Do not modify the vendored BaseJump files as
part of the verification task; hidden mutants target the wrapper-level behavior
rather than BaseJump internals.

The vendored BaseJump STL subset is licensed under the Solderpad Hardware
License, Version 0.51. The upstream license is preserved at
[`vendor/basejump_stl/LICENSE`](vendor/basejump_stl/LICENSE), and the repository
root also includes `THIRD_PARTY_NOTICES.md`.

## Specification Under Test

The DUT is a two-lane FIFO with one output.

- `reset_i` is active-high and synchronous to `clk_i`.
- Lane 0 uses `data0_i`, `valid0_i`, and `ready0_o`.
- Lane 1 uses `data1_i`, `valid1_i`, and `ready1_o`.
- A producer word is accepted when `valid*_i && ready*_o` is true at a rising
  clock edge.
- The output word is consumed when `valid_o && yumi_i` is true at a rising
  clock edge.
- The FIFO accepts at most one input word per cycle.
- If both lanes are valid and the FIFO can accept input, the arbiter grants
  exactly one lane using round-robin policy. Lane 0 wins the first contention
  after reset.
- If exactly one lane is valid and the FIFO can accept input, that lane must be
  accepted regardless of round-robin preference.
- If the FIFO is full and the output is consumed in the same cycle, the FIFO
  must also be able to accept one new input word.
- `valid_o`, `data_o`, and `count_o` must reflect FIFO occupancy and oldest-word
  order.
- `selected_lane_o` is a combinational debug signal for the current arbitration
  decision.

## Agent Task

Complete `dv/cocotb/test_stream_arb_fifo.py`. A strong solution should include:

- clock and synchronous reset helpers,
- input-driving helpers for both producer lanes,
- an independent Python reference model of FIFO order/count/arbitration,
- checks for ready/valid/yumi behavior before and after clock edges,
- coverage markers written through the provided `mark_coverage` helper.

## Commands

Run the visible CocoTB test:

    make test

Run the hidden reference grader in this repository checkout:

    python3 donotaccess/grade.py --root . --pretty

In a deployed HUD task, the files under `donotaccess/` are hidden from the
agent. The hidden files are present in this repository so vendors can inspect
the reference task structure.
