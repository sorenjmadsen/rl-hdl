Repair the CocoTB verification environment for a BaseJump-backed two-input,
one-output ready/valid/yumi FIFO. Edit `dv/cocotb/test_stream_arb_fifo.py` so it
implements meaningful drivers/checks, an independent FIFO reference model,
coverage marking, and assertions for lane-1 traffic, round-robin contention,
full pop+push, reset restart, and pointer wraparound. Mark covered scenarios
with `mark_coverage`: `reset`, `lane0_basic`, `lane1_only`,
`round_robin_contention`, `full_pop_push`, `reset_restarts_arbitration`, and
`wraparound_order`. Do not edit RTL, vendor files, mutants, the Makefile, or
helper scripts.
