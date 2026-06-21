# Bug Catalog

This repair task seeds three bugs in the agent-facing two-lane stream FIFO RTL.

1. **Lane 1 starvation**
   - The buggy design grants only lane 0 and never asserts `ready1_o`.
   - Effect: traffic from the second producer is dropped/stalled forever, and
     contention never follows the required round-robin policy.

2. **No full-cycle pop+push**
   - The buggy design computes input readiness from `count < depth` only.
   - Effect: when the FIFO is full, it refuses a new input even if `yumi_i`
     consumes the current output in the same cycle and frees a slot.

3. **Latent latch in arbitration debug output**
   - `selected_lane_o` is assigned by incomplete combinational logic.
   - Effect: the data path may appear correct after functional fixes, but
     synthesis infers a latch and Verilator lint reports `LATCH`.

The bugs cover both functional protocol failures and hardware-quality failures.
A patch that fixes the stream behavior but leaves the latch should score about
0.7: full functional credit, partial synthesis credit, and no lint credit.
