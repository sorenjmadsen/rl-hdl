# Mutant Catalog

This DV task grades a submitted CocoTB testbench against a correct
BaseJump-backed wrapper DUT and a set of hidden mutant DUTs. Mutants target the
wrapper-level stream protocol and arbitration behavior, not BaseJump STL
internals.

1. **Lane 1 starvation**
   - Lane 1 is never granted even when it is the only valid input.
   - A good testbench catches this with lane-1-only traffic.

2. **No full-cycle pop+push**
   - The DUT refuses an input when full even if the output is consumed in the
     same cycle.
   - A good testbench fills the FIFO, drives `yumi_i`, and expects a producer
     lane to be ready in that same cycle.

3. **Round-robin stuck on lane 0**
   - Contention always grants lane 0 instead of alternating.
   - A good testbench drives both valid lanes across multiple cycles and checks
     ready outputs and output order.

4. **Reset restarts with the wrong arbitration preference**
   - The first contention after reset incorrectly prefers lane 1.
   - A good testbench verifies lane 0 wins first contention after every reset.

5. **Bad pointer wraparound**
   - The FIFO pointer wraps one entry early.
   - A good testbench fills, drains partially, refills, and checks output order
     through the wrap boundary.
