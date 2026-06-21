# Formal Mutant Catalog

The hidden grader checks the submitted formal properties against these
BaseJump-backed wrapper mutants.

- `stream_arb_fifo_lane1_starved.sv`: lane 1 is selected but never marked
  ready when it is the only valid lane.
- `stream_arb_fifo_no_full_pop_push.sv`: the wrapper cannot accept an input in
  the same cycle that a full FIFO pops an output.
- `stream_arb_fifo_rr_stuck_lane0.sv`: contention always grants lane 0,
  ignoring the round-robin preference.
- `stream_arb_fifo_reset_pref_lane1.sv`: reset incorrectly restarts arbitration
  with lane 1 preferred.
- `stream_arb_fifo_bad_data_mux.sv`: accepted lane data is swapped before it
  enters the BaseJump FIFO.
