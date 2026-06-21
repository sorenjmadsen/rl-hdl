Repair synthesizable SystemVerilog RTL for a two-input, one-output ready/valid
FIFO. The FIFO is width 8, depth 8, with synchronous active-high reset. Preserve
FIFO order and count, accept either lone valid lane, round-robin arbitrate when
both lanes are valid, allow full pop+push in one cycle, and avoid combinational
latches.
