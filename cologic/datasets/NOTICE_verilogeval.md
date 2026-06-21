# VerilogEval attribution

`verilogeval_combinational.json` is derived from **VerilogEval** (the
`dataset_spec-to-rtl` problems): prompts, reference solutions, and testbenches.

- Source: https://github.com/NVlabs/verilog-eval
- License: **MIT** — Copyright (c) 2023-2024 NVIDIA Research Projects (with code
  from OpenAI's human-eval project).

The MIT license permits redistribution with this notice. We vendor only the
combinational subset, converted into rl_hdl `Task` records (reference module
renamed `RefModule` -> `TopModule`). Regenerate with
`scripts/build_verilogeval_subset.py`.
