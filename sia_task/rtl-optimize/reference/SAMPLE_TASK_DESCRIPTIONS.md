# Example task descriptions

The target agent optimizes a correct Verilog module for **gate count** while
preserving **exact functional equivalence** (checked by Verilator + Yosys via the
immutable grader). The biggest synth-surviving wins are arithmetic-structural:

- **Share arithmetic operators.** A datapath that selects one of two products,
  `y = s ? (a*b) : (c*d)`, instantiates two multipliers but only uses one; rewrite
  it to share a single multiplier with muxed operands: `y = (s?a:c) * (s?b:d)`.
- **Remove redundant/duplicated arithmetic**, fold constants.
- **Strength-reduce** constant multiplies/divides to shifts and adds.

A rewrite only earns reward if the grader confirms it is exactly equivalent to the
baseline and smaller. The agent keeps each module's name and interface identical.
