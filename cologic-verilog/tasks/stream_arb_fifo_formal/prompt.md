Complete the Yosys-supported SystemVerilog formal checks for a BaseJump-backed
two-input ready/valid FIFO in `formal/stream_arb_fifo_props.sv`. Use immediate
`assert`, `assume`, and `cover` statements inside procedural blocks; do not use
`property/endproperty` syntax. Check reset, count, arbitration, full pop+push,
data ordering, and wraparound behavior with bounded formal assertions. Include
non-vacuous cover statements. Do not edit the RTL, vendor files, or build
scripts.
