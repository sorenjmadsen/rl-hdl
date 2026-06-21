# Task: optimize Verilog designs for gate count, provably equivalent

You are improving a **target agent** (an automated RTL optimizer). Each generation,
the target agent is run as:

    python target_agent.py --dataset_dir <data/public> --working_dir <gen_dir>

and must, for every design listed in `--dataset_dir/manifest.json`, produce a
**smaller but exactly equivalent** Verilog module and write it to
`<working_dir>/submission/<design_id>.v`.

## What the target agent must do
- Read `manifest.json` (a list of `design_ids`). Each id resolves to a correct
  baseline module via `cologic.designs.BY_ID[id]` (gives `.reference_rtl`,
  `.top_module`, `.interface`).
- Rewrite each baseline to use **fewer gates** while keeping the **module name,
  port names, directions, and widths identical**.
- Write one optimized module per design to `submission/<design_id>.v`.
- It may sample candidates from the policy model (OpenAI-compatible client; model +
  base URL + key come from the environment), and it **should self-check** each
  candidate with the grader before submitting (see below).

## How verification works — DO NOT CHANGE THIS (read carefully)
There is **NO local Verilator or Yosys in this environment**. The ONLY way to check
equivalence or gate count is the **deployed Modal verifier**, called by name:

```python
import modal
_grader = modal.Function.from_name("rl-hdl", "grade_opt_remote")
out = _grader.remote(candidate_rtl, task)   # {"reward", "info", "task_id"}
# out["info"]["equivalent"], ["ref_cells"], ["cand_cells"], ["area_improvement"]
```

This is the immutable grader (real Verilator equivalence + Yosys gate count). When you
revise this agent, **keep using `grade_opt_remote` for every candidate check.**

**FORBIDDEN — these earn ZERO credit:**
- Do **NOT** invent an LLM-based equivalence check ("ask the model if it's equivalent").
- Do **NOT** estimate, guess, or hard-code area reductions.
- Do **NOT** fall back to "grader unavailable → assume equivalent". If `grade_opt_remote`
  errors, fail loudly — do not substitute a guess.

Why: `evaluate.py` recomputes the official reward with the SAME deployed verifier,
independently of whatever this agent does. Any candidate you picked using an LLM
guess or estimate will simply score whatever the real silicon tooling says — usually
nothing. Optimizing against anything other than `grade_opt_remote` is wasted effort.

## Where the real headroom is
Yosys's default synthesis already minimizes boolean logic, so cosmetic rewrites
win nothing. The wins that survive synthesis are **arithmetic-structural**:
- **Share arithmetic operators** under mutually-exclusive selects (e.g. compute one
  of two products with a single multiplier and muxed operands instead of two).
- Remove **redundant / duplicated arithmetic**.
- Strength-reduce constant multiplies/divides to shifts and adds.

## Hard rules
- Keep each module's name and interface exactly as the baseline.
- One module per `submission/<design_id>.v`, in a ```verilog code block or raw.
- Never try to influence `evaluate.py` or the grader — equivalence is checked by
  real silicon tooling and cannot be faked.
