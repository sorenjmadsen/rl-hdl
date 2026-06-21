# BaseJump Stream FIFO Formal Task

This is a reference HDL task for the Verilog Tasks RFP. It exercises the
Formal track using a BaseJump-backed DUT wrapper.

The agent edits [`formal/stream_arb_fifo_props.sv`](formal/stream_arb_fifo_props.sv).
The DUT in [`rtl/stream_arb_fifo.sv`](rtl/stream_arb_fifo.sv) composes a
vendored `bsg_fifo_1r1w_small` from BaseJump STL with custom two-lane
ready/valid arbitration logic.

## Specification

Write Yosys-supported SystemVerilog formal checks for the two-lane stream FIFO.
Use immediate `assert`, `assume`, and `cover` statements inside procedural
blocks; do not use unsupported `property/endproperty` concurrent SVA syntax.

The formal harness should check:

- synchronous active-high reset clears externally visible state,
- `count_o` matches the modeled FIFO occupancy and never exceeds `depth_p`,
- `valid_o` is asserted exactly when the modeled FIFO is non-empty,
- lane 0 and lane 1 are both accepted when they are the lone valid lane,
- simultaneous lane contention follows round-robin arbitration, starting with
  lane 0 after reset,
- a full FIFO can accept a new input in the same cycle that `yumi_i` consumes
  the output word,
- output data preserves FIFO order across pointer wraparound,
- cover statements demonstrate non-vacuous lane 1, contention, full pop+push,
  and wraparound scenarios.

The public harness uses `width_p == 8` and `depth_p == 4` to keep the formal
state space small while still exercising wraparound and full FIFO behavior.

## Commands

Run the bounded proof check:

```sh
make prove
```

Run cover reachability:

```sh
make cover
```

Run both visible checks:

```sh
make test
```

Run the hidden reference grader in this repository checkout:

```sh
python3 donotaccess/grade.py --root . --pretty
```

In a deployed HUD task, the files under `donotaccess/` are hidden from the
agent. They remain checked in here so vendors can inspect the reference grader
structure.
