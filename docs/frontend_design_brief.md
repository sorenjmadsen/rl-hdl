# Frontend design brief — RTL Optimizer UI (for Claude Design)

A build brief for the single-page UI that drives the RTL optimizer. The backend is
**already deployed and live**; this doc is the implementation contract for the
frontend. The visual style should match the existing dark "foundry" theme in
`web/` (see `web/uploads/DESIGN_NOTES.md`: dark green-black background, green
monospace, thin borders, flat blocks — a technical-diagram feel, not skeuomorphic).

## Goal

Let a user optimize a Verilog design end to end, in the browser:

1. **Upload** one or more Verilog files **+** an optional testbench stimulus.
2. Enter a **prompt** describing the optimization goal.
3. Watch it run and get **refined Verilog** back, with proof it's still correct and smaller.

Under the hood the default path is the **SIA loop** (an LLM "meta agent" evolves the
optimizer across generations; a frozen immutable grader — Verilator equivalence +
Yosys gate count — is the only judge). A faster single-shot "harness" mode also exists.

---

## Backend API (the contract — do not change)

- **Base URL:** `https://yc-hack27--rl-hdl-web.modal.run`
- **Auth:** every request sends header `X-RLHDL-Token: <token>`. Missing/wrong → `401`.
  Provide a token field in the UI (store in memory/localStorage; do not hardcode).
- **CORS:** open (`*`), so the browser can call it directly.
- **Cold start:** the first request after idle may take a few seconds.

### `POST /optimize` — start a job

`multipart/form-data`:

| field | type | required | notes |
|---|---|---|---|
| `files` | file (repeatable) | ✅ | one or more `.v`/`.sv`. Send the field name `files` once per file. |
| `prompt` | text | ✅ | the optimization goal; becomes the spec shown to the model. |
| `stimulus` | text | for clocked designs | scaffold-fill testbench body (see below). |
| `top_module` | text | optional | only needed if the top can't be inferred (multi-module ambiguity). |
| `mode` | text | optional | `"sia"` (default) or `"harness"`. |
| `n_candidates` | int | optional | default 4. |
| `temperature` | float | optional | default 0.9. |
| `max_repair_rounds` | int | optional | default 1. |
| `max_generations` | int | optional | default 2. SIA generations are expensive — keep small. |
| `patience` | int | optional | harness mode only, default 3. |
| `meta_model` | text | optional | SIA meta agent, default `"sonnet"`. |
| `meta_max_turns` | int | optional | SIA only, default 60. |
| `model` | text | optional | target policy (Fireworks), has a default. |

**200 response:**
```json
{ "job_id": "fc-...", "mode": "sia", "top_module": "mux4", "clocked": false, "baseline_cells": 60 }
```
Use `top_module` / `clocked` / `baseline_cells` to confirm the parse back to the user
immediately (e.g. "Parsed top module `mux4`, 60 cells baseline").

**Errors:**
- `400` — bad upload or **pre-flight failure** (the design doesn't grade equivalent to
  itself; usually a malformed interface or stimulus). Body: `{"detail": "<message + tool log>"}`.
  Show `detail` to the user — it's actionable.
- `401` — missing/invalid token.

### `GET /jobs/{job_id}` — poll for status

Header `X-RLHDL-Token` required. Returns one of:
```json
{ "status": "running" }
{ "status": "error", "error": "<message>" }
{ "status": "done", "result": { ... } }   // shape depends on mode
```

**Poll cadence:** every ~5–10 s. **Expect long runs:** harness ≈ 1–3 min; **SIA ≈ 10–15 min**.
Show elapsed time and keep polling; don't time out the UI before ~30 min.

#### `result` — SIA mode
```json
{
  "returncode": 0,
  "best_gen": "gen_1",
  "best_mean_reward": 0.8,
  "best_rtl": { "mux4": "module mux4(...);\n ... endmodule\n" },   // {design_id: RTL}
  "generations": [
    { "gen": "gen_1",
      "results": { "mean_reward": 0.8, "mean_area_improvement": 0.6,
                   "n_equivalent": 1, "n_total": 1,
                   "designs": [ { "id": "mux4", "reward": 0.8, "stage": "graded",
                                  "equivalent": true, "ref_cells": 60, "cand_cells": 24,
                                  "area_improvement": 0.6 } ] },
      "has_target_agent": true,
      "submission": { "mux4": "module mux4(...) ... endmodule\n" } },
    { "gen": "gen_2", "results": { ... }, "submission": { ... } }
  ],
  "artifacts": { "gen_1/target_agent.py": "...", "target_agent_gen1_to_gen2.diff": "...", "...": "..." },
  "stdout_tail": "..."
}
```

#### `result` — harness mode
```json
{
  "baseline_cells": 60, "best_cells": 24, "total_improvement": 0.6, "plateaued": false,
  "history": [ { "gen": 0, "cells": 60, "reward": 0.5, "equivalent": true, "improved": false },
               { "gen": 1, "cells": 24, "reward": 0.8, "equivalent": true, "improved": true } ],
  "best_rtl": "```verilog\nmodule mux4(...) ... endmodule\n```"
}
```

> ⚠️ **`best_rtl` differs by mode.** SIA: a **dict** `{design_id: rtl}` (use `best_rtl[top_module]`).
> Harness: a **string**. Also, the model's output may be wrapped in a ```` ```verilog ```` fence —
> strip the fence before displaying/downloading.

---

## UI requirements

### 1. Upload
- A multi-file dropzone for `.v`/`.sv` (the design + any submodules).
- A **separate** "Testbench (clocked designs)" input — a textarea or file slot for the
  scaffold-fill stimulus. Show inline help (next section).
- After the POST returns, echo back `top_module`, `clocked`, and `baseline_cells`.

### 2. Prompt
- A textarea, e.g. placeholder "Optimize this 2×2 matmul for gate count while preserving behavior."

### 3. Output
- **Refined Verilog**: a code block with copy + "Download `.v`" (fence-stripped).
- **Progress / proof**:
  - SIA: a per-generation table or small line chart — `gen`, `mean_reward`, `cand_cells`,
    `equivalent (n/n)`, `area_improvement`. Highlight `best_gen`.
  - Harness: the gate-count curve from `history` (cells per generation), `equivalent` ✓,
    and `baseline_cells → best_cells (−X%)`.
- **Equivalence badge**: "Equivalent ✓ (Verilator)" and "Cells: 60 → 24 (−60%)".
- **Bonus (SIA)**: a collapsible "How the optimizer evolved" showing
  `artifacts["target_agent_gen1_to_gen2.diff"]` — the scaffold the meta agent rewrote.

### Controls
- **Mode toggle**: SIA (default) / Harness, with a one-line explainer each.
- **Advanced knobs** (collapsed by default): `max_generations`, `n_candidates`,
  `temperature`, `meta_model`, `meta_max_turns`, `max_repair_rounds`.
- **Token** field.

### States
`idle → submitting → running (polling, show elapsed + latest generation) → done | error`.
On `400`, surface the `detail` body (it includes the tool log). On `error` status, show `error`.

---

## Scaffold-fill stimulus (inline help for clocked designs)

Combinational designs need no testbench (random vectors are auto-generated). **Clocked**
designs (a `clk`/`clock` port) require a stimulus. The harness owns the differential
candidate-vs-reference instantiation, the free-running clock, the output comparator
(`rlhdl_sample`), and the pass/fail accounting. The user supplies **only** a stimulus that:

- defines `task stimulus;` (the entry point the harness calls),
- drives the input ports by name,
- advances time with `@(posedge clk);` (never drives the clock itself),
- calls `rlhdl_sample;` whenever candidate and reference outputs should match.

Example to show in the UI:
```systemverilog
task stimulus;
  integer i;
  begin
    rst_n = 0; x = 0; @(posedge clk); #1;
    rst_n = 1;
    for (i = 0; i < 16; i = i + 1) begin
      x = i[7:0]; @(posedge clk); #1; rlhdl_sample;
    end
  end
endtask
```

---

## Notes & gotchas
- SIA spends real LLM budget (Anthropic meta agent + Fireworks target) per generation —
  keep `max_generations` low by default and warn before launching a large run.
- A generation can regress (the grader scores a bad scaffold low and keeps the best so
  far) — show `best_gen`, not just the last generation.
- `result.best_rtl` is the source of truth for the download; per-generation `submission`
  is for the progress view.
- Reward semantics: `0.05` compile/synth failure · `0.10` not equivalent · `0.50` equivalent,
  no size win · up to `1.0` equivalent and much smaller.
