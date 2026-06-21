# Third-Party Notices

This repository vendors a small subset of third-party HDL code for the
reference tasks. Runtime HUD tasks should use the checked-in vendored files and
must not fetch third-party libraries from the internet.

## BaseJump STL

Paths:

- `tasks/stream_arb_fifo_cocotb_dv/vendor/basejump_stl`
- `tasks/stream_arb_fifo_formal/vendor/basejump_stl`

Upstream project: <https://github.com/bespoke-silicon-group/basejump_stl>

Use in this repository: the CocoTB DV and Formal reference tasks use minimal
vendored subsets of BaseJump STL to build a two-lane stream FIFO wrapper around
`bsg_fifo_1r1w_small`. The tasks' hidden mutants target the wrapper's stream
protocol, arbitration, and formal-observable behavior, not BaseJump STL
internals.

License: Solderpad Hardware License, Version 0.51.

Copyright notice from the upstream license:

> Copyright 2016 Michael B. Taylor. Copyright and related rights are licensed
> under the Solderpad Hardware License, Version 0.51.

The upstream license text is preserved in each vendored
`vendor/basejump_stl/LICENSE` file.
