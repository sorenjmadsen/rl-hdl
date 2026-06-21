# Two-Lane Stream FIFO Repair

This is a reference HDL task for the Verilog Tasks RFP. It exercises the
Design track, repair/debug variant.

The agent edits [`rtl/stream_arb_fifo.sv`](rtl/stream_arb_fifo.sv). The module
is a near-working stream FIFO using a ready/valid/yumi handshake interface,
extended from a single input into two arbitrated producer lanes. Fix the
implementation so it satisfies the specification below and passes the visible
and hidden checks.

The checked-in RTL is intentionally defective because this is a repair task.
Before the repair, visible simulation is expected to fail. A correct solution
should pass `make test`, `make synth`, and `make lint`, while the hidden grader
also checks corner cases and weighted rubric scoring.

## Specification

Implement a two-lane ready/valid stream FIFO with one output.

- `reset_i` is an active-high synchronous reset sampled on `clk_i`.
- On reset, clear the FIFO state: occupancy count is 0, output is invalid,
  read/write pointers are cleared to entry 0, and lane arbitration restarts
  with lane 0 preferred.
- Producer lane 0 uses `data0_i`, `valid0_i`, and `ready0_o`.
- Producer lane 1 uses `data1_i`, `valid1_i`, and `ready1_o`.
- A lane input is accepted on a rising clock edge when its `valid*_i` and
  `ready*_o` are both asserted.
- The output uses `valid_o`, `data_o`, and `yumi_i`. An output word is consumed
  on a rising clock edge when `valid_o && yumi_i`.
- `valid_o` must be asserted exactly when the FIFO contains at least one word.
- `data_o` must expose the oldest queued word whenever `valid_o` is asserted.
- `count_o` must equal the current FIFO occupancy.
- The design may accept at most one input word per cycle.
- If both lanes are valid and the FIFO can accept an input, grant exactly one
  lane using round-robin arbitration. Lane 0 wins the first contention after
  reset; the next contention prefers the other lane after every accepted word.
- If exactly one lane is valid and the FIFO can accept an input, accept that
  lane regardless of the current round-robin preference.
- If the FIFO is full and `yumi_i && valid_o` consumes the output word, the
  design must also be able to accept one input word in the same cycle.
- There is no same-cycle pass-through from an accepted input to `data_o` when
  the FIFO was empty at the start of the cycle.
- `selected_lane_o` is a debug output indicating the lane selected by the
  current arbitration decision. It must be combinational and latch-free.
- Supported parameter range for this reference task: `width_p == 8`,
  `depth_p == 8`.

## Commands

Run the visible test:

```sh
make test
```

Run synthesis and latch detection:

```sh
make synth
```

Run Verilator lint:

```sh
make lint
```

Run the hidden reference grader in this repository checkout:

```sh
python3 donotaccess/grade.py --root .
```

In a deployed HUD task, the files under `donotaccess/` are hidden from the
agent. The hidden files are present in this repository so vendors can inspect
the reference task structure.
